import os, hashlib, time, base64, requests
import xml.etree.ElementTree as ET
from flask import Flask, request, Response

app = Flask(__name__)

TOKEN     = os.environ.get('WX_TOKEN', '')
APPID     = os.environ.get('WX_APPID', '')
SECRET    = os.environ.get('WX_APPSECRET', '')
IMGBB_KEY = os.environ.get('IMGBB_API_KEY', '')

def check_sig(sig, ts, nonce):
    s = ''.join(sorted([TOKEN, ts, nonce]))
    return hashlib.sha1(s.encode()).hexdigest() == sig

def get_access_token():
    r = requests.get(
        'https://api.weixin.qq.com/cgi-bin/token',
        params={'grant_type': 'client_credential', 'appid': APPID, 'secret': SECRET},
        timeout=5
    )
    return r.json().get('access_token', '')

def download_media(token, media_id):
    r = requests.get(
        'https://api.weixin.qq.com/cgi-bin/media/get',
        params={'access_token': token, 'media_id': media_id},
        timeout=10
    )
    ct = r.headers.get('Content-Type', '')
    if r.status_code == 200 and ('image' in ct or 'octet-stream' in ct):
        return r.content
    return None

def upload_to_imgbb(data):
    r = requests.post(
        'https://api.imgbb.com/1/upload',
        data={'key': IMGBB_KEY, 'image': base64.b64encode(data).decode()},
        timeout=15
    )
    j = r.json()
    return j['data']['url'] if j.get('success') else None

def xml_reply(to, frm, content):
    return f'''<xml>
<ToUserName><![CDATA[{to}]]></ToUserName>
<FromUserName><![CDATA[{frm}]]></FromUserName>
<CreateTime>{int(time.time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>'''

@app.route('/api/wx', methods=['GET'])
def wx_verify():
    sig   = request.args.get('signature', '')
    ts    = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echo  = request.args.get('echostr', '')
    if check_sig(sig, ts, nonce):
        return echo
    return 'Forbidden', 403

@app.route('/api/wx', methods=['POST'])
def wx_message():
    try:
        root  = ET.fromstring(request.data)
        to    = root.findtext('ToUserName')
        frm   = root.findtext('FromUserName')
        mtype = root.findtext('MsgType')

        if mtype == 'image':
            media_id = root.findtext('MediaId')
            token    = get_access_token()
            img_data = download_media(token, media_id)
            if img_data:
                url = upload_to_imgbb(img_data)
                content = (
                    f'表情处理完成：🔗 点击下载\n{url}\n\n保存出现问题？回复「帮助」获取教程'
                    if url else '图片上传失败，请稍后重试'
                )
            else:
                content = '图片获取失败，请稍后重试'

        elif mtype == 'text':
            text = root.findtext('Content', '').strip()
            if '帮助' in text or 'help' in text.lower():
                content = (
                    '📖 使用教程\n\n'
                    '1. 直接发送图片或表情给我\n'
                    '2. 我会返回一个下载链接\n'
                    '3. 点击链接，长按图片保存即可\n\n'
                    '支持：普通图片、表情包、截图等'
                )
            else:
                content = '发送图片给我，我来帮你生成下载链接 😊'
        else:
            content = '发送图片给我，我来帮你生成下载链接 😊'

        return Response(xml_reply(frm, to, content), mimetype='text/xml')
    except Exception:
        return 'success', 200
