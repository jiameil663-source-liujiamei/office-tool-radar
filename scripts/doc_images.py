#!/usr/bin/env python3
"""
飞书文档插图工具:把本地截图作为图片块插入已有文档的指定锚点后。
用法:python3 doc_images.py <doc_id> <锚点文本> <图片路径> [锚点文本 图片路径 ...]
锚点 = 文档中某段文字的前缀(取第一个匹配块),图片插在该块之后。
环境变量:FEISHU_APP_ID + FEISHU_APP_SECRET(群小汇)
仅标准库;multipart 用手工边界构造。
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

OPEN_API = "https://open.feishu.cn/open-apis"


def token(app_id, app_secret):
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(OPEN_API + "/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["tenant_access_token"]


def api(method, path, payload=None, tok=None, headers=None, data=None, params=""):
    url = OPEN_API + path + params
    hdrs = {"Authorization": "Bearer " + (tok or "")}
    if headers:
        hdrs.update(headers)
    else:
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    body = data if data is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def list_blocks(doc_id, tok):
    """返回文档全部顶层块 [(block_id, text)]"""
    out, cursor = [], None
    while True:
        params = "?page_size=500" + (("&page_token=" + cursor) if cursor else "")
        r = api("GET", "/docx/v1/documents/%s/blocks" % doc_id, None, tok, params=params)
        if r.get("code") != 0:
            print("取块失败:", r.get("code"), r.get("msg"))
            return out
        items = r.get("data", {}).get("items", [])
        out.extend(items)
        if r["data"].get("has_more"):
            cursor = r["data"].get("page_token")
        else:
            return out


def block_text(b):
    for key in ("text", "heading1", "heading2", "heading3", "bullet", "ordered"):
        sec = b.get(key)
        if sec and "elements" in sec:
            return "".join(e.get("text_run", {}).get("content", "") for e in sec["elements"])
    return ""


def upload_image(path, doc_id, tok):
    """drive medias upload_all → file_token"""
    fn = os.path.basename(path)
    with open(path, "rb") as f:
        content = f.read()
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in [
        ("file_name", fn), ("parent_type", "docx_image"), ("parent_node", doc_id), ("size", str(len(content))),
    ]:
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, name, value)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: image/png\r\n\r\n" % (boundary, fn)).encode())
    parts.append(content)
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    data = b"".join(parts)
    r = api("POST", "/drive/v1/medias/upload_all", None, tok,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary}, data=data)
    if r.get("code") != 0:
        print("上传失败 %s:" % fn, r.get("code"), r.get("msg"))
        return None
    return r["data"]["file_token"]


def png_size(path):
    """读 PNG IHDR 宽高"""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return 1600, 1000
    import struct
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def insert_image_after(doc_id, anchor_prefix, img_path, tok):
    """在页面层级找到锚点块的序号,把图片作为同级块插到锚点后面"""
    blocks = list_blocks(doc_id, tok)
    idx = next((i for i, b in enumerate(blocks) if block_text(b).startswith(anchor_prefix)), None)
    if idx is None:
        print("⚠ 找不到锚点:", anchor_prefix[:30])
        return False
    file_token = upload_image(img_path, doc_id, tok)
    if not file_token:
        return False
    w, h = png_size(img_path)
    scale = min(1.0, 1800 / w)
    r = api("POST", "/docx/v1/documents/%s/blocks/%s/children" % (doc_id, doc_id),
            {"children": [{"block_type": 27, "image": {
                "token": file_token, "width": int(w * scale), "height": int(h * scale)}}],
             "index": idx + 1}, tok)
    ok = r.get("code") == 0
    print(("✓ 插入 " if ok else "✗ 失败 ") + os.path.basename(img_path) + (" " if ok else str(r.get("msg"))))
    return ok


def main():
    args = sys.argv[1:]
    if len(args) < 3 or len(args) % 2 == 0:
        print(__doc__)
        sys.exit(1)
    doc_id = args[0]
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    tok = token(app_id, app_secret)
    pairs = [(args[i], args[i + 1]) for i in range(1, len(args), 2)]
    fails = [p for p in pairs if not insert_image_after(doc_id, p[0], p[1], tok)]
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
