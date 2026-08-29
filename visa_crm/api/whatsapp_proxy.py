import frappe
import requests
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
def view():
	"""
	In-App WhatsApp Web Proxy:
	Fetches web.whatsapp.com, injects base tag, strips frame-ancestors / X-Frame-Options,
	and serves to the in-built CRM iframe so WhatsApp Web renders seamlessly without being blocked.
	"""
	headers = {
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
		'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
		'Accept-Language': 'en-US,en;q=0.9',
		'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
		'Sec-Ch-Ua-Mobile': '?0',
		'Sec-Ch-Ua-Platform': '"Windows"',
		'Sec-Fetch-Dest': 'document',
		'Sec-Fetch-Mode': 'navigate',
		'Sec-Fetch-Site': 'none',
		'Sec-Fetch-User': '?1',
		'Upgrade-Insecure-Requests': '1',
	}
	try:
		r = requests.get('https://web.whatsapp.com/', headers=headers, timeout=20)
		html = r.text
		if '<head>' in html:
			html = html.replace('<head>', '<head><base href="https://web.whatsapp.com/">', 1)
		
		# Strip any frame busting scripts if present
		html = html.replace('window.top.location', 'window.location')
		html = html.replace('top.location.href', 'window.location.href')

		resp = Response(html, mimetype='text/html', status=200)
		resp.headers['X-Frame-Options'] = 'ALLOWALL'
		resp.headers['Access-Control-Allow-Origin'] = '*'
		resp.headers['Content-Security-Policy'] = "frame-ancestors *;"
		return resp
	except Exception as e:
		return Response(
			f"<html><body style='font-family:sans-serif;padding:20px;'><p>Failed to proxy WhatsApp Web: {e}</p></body></html>",
			mimetype='text/html',
			status=500
		)
