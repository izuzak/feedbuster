import cgi
import os
import feedparser
import re

from xml.dom import minidom
from elementtree import ElementTree 
from xml.sax import saxutils 

from google.appengine.api import urlfetch

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class MediaInjection(webapp.RequestHandler): 

  def get(self):
    feedUrl = self.request.get('inputFeedUrl')

    # fetch feed XML string
    fetchResult = urlfetch.fetch(feedUrl) 
    
    # check if fetched ok
    if fetchResult.status_code != 200:
      self.response.out.write("invalidu!")
      return
    
    feedXMLString = fetchResult.content
    feed = feedparser.parse(feedXMLString)
    
    for entry in feed.entries:
      if entry.has_key('summary'):
				stringToParse = saxutils.unescape(entry.content[0].value) 
			  imgSrcs = re.findall('<\s*img [^\>]*src\s*=\s*["\'](.*?)["\']', stringToParse)
        for imgSrc in imgSrcs:
					self.response.out.write(imgSrc.group(0) + '\n')
        

    # parse feed XML into DOM
    # feedXMLString = fetchResult.content
    # feedDOM = minidom.parseString(feedXMLString) 
    # >>> a = a.decode("string-escape")
    #self.response.out.write(feedDOM.toxml())
    
		# <\s*img [^\>]*src\s*=\s*(["\'])(.*?)\1
		
		
		# ElementTree  - elem = fromstring(text) # same as XML(text)
		
		# <TAG\b[^>]*>(.*?)</TAG>
		# http://docs.python.org/dev/howto/regex.html
		# http://docs.python.org/library/htmlparser.html
		# http://docs.python.org/library/htmllib.html#module-htmllib
		# http://www.crummy.com/software/BeautifulSoup/
		# http://code.google.com/p/html5lib/
		# http://groups.google.com/group/google-appengine/browse_thread/thread/63d7afda2ca17dc4/7e73696b46f70c54?lnk=gst&q=parse+html#7e73696b46f70c54
		# http://lethain.com/entry/2008/jun/09/deployment-scripts-with-beautifulsoup/
		# http://stackoverflow.com/questions/300445/how-to-unquote-a-urlencoded-unicode-string-in-python
		# http://blog.ianbicking.org/2008/03/30/python-html-parser-performance/
		# http://blog.ianbicking.org/2008/12/10/lxml-an-underappreciated-web-scraping-library/
		# http://blog.emmesdee.com/2008/08/more-google-app-engine-rss.html
		# http://stackoverflow.com/questions/138313/how-to-extract-img-src-title-and-alt-from-html-using-php
		# http://stackoverflow.com/questions/257409/download-image-file-from-the-html-page-source-using-python
		# http://stackoverflow.com/questions/326103/why-is-this-regex-returning-errors-when-i-use-it-to-fish-img-srcs-from-html
		# http://wiki.python.org/moin/EscapingXml
		# feedTree = ElementTree.XML(feedXMLString)
		# for outline in tree.findall("//outline"): 
		# print outline.get('xmlUrl') 
		
    # contentElements = feedDOM.getElementsByTagName("description")
    # for content in contentElements:
    #  self.response.out.write(content.toxml() + "\n")
      
    # pokupi sve slike iz summarya i contenta, izbaci duplikate
    # problem sa namespaceima ns:item
    
    #check if rss or atom
    
    #extract media info
    
    #generate media items
    
    #insert items into feed
    
    # self.response.out.write(feedXMLString)

application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()