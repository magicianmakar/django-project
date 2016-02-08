import bleach

ALLOW_ATTRS = {
    '*': ['id', 'class', 'style', 'dir'],
    'a': ['href'],
    'img': ['src', 'alt'],
}

ALLOW_TAGS = ['em','pre','h1','h2','h3','h4','h5','h6','span','sub','p','li',
			  'sup','blockquote','address','strong','a','ol','ul','s','u','div']
			  
ALLOW_STYLES = ['font-size','color','margin-left','margin-right','font-family',
				'background-color','text-align']

def xss_clean(text):
	return bleach.clean(text, ALLOW_TAGS, ALLOW_ATTRS, ALLOW_STYLES)
