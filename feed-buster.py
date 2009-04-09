import cgi
import os
import feedparser
import re
import urllib
import mimetypes

from xml.dom import minidom
from xml.etree import ElementTree 
from xml.sax import saxutils 

from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class MediaInjection(webapp.RequestHandler): 

  def get(self):
    # get feed url
    feedUrl = self.request.get('inputFeedUrl')
    
    # decode feed url
    feedUrl = urllib.unquote(feedUrl)
    
    # fetch feed XML string
    fetchResult = urlfetch.fetch(feedUrl) 
    
    # check if fetch succeeded
    # if fetchResult.status_code != 200:
    #  self.response.set_status(500) # check for appropriate status msg
    #  return
    
    feedXMLString = fetchResult.content
    
    # fpFeed = feedparser.parse(feedXMLString)
    feedTree = ElementTree.fromstring(feedXMLString)
    #self.response.out.write(ElementTree.tostring(feedTree))

    # is the feed RSS
    if len(feedTree.findall('.//item')) > 0:
      #self.response.out.write("RSS")
      parsingParams = { 'items' : 'item', 'crawlTags' : ['description', '{http://purl.org/rss/1.0/modules/content/}encoded', 'body', 'fullitem'],
                        'generateParams' : {'tag' : '{http://search.yahoo.com/mrss/}content', 'attrs': {}, 'src' : 'url'}}
    # is the feed ATOM
    elif len(feedTree.findall('.//entry')) > 0:
      #self.response.out.write("ATOM")
      parsingParams = { 'items' : 'entry', 'crawlTags' : ['summary', 'content'],
                        'generateParams' : {'tag' : 'link', 'attrs': {'rel' : 'enclosure'}, 'src' : 'href'}}
    # not RSS or ATOM -> error
    else:
      #self.response.out.write("LOL")
      #self.response.set_status(500)
      return 
    
    # find and generate media items
    items = feedTree.findall('.//' + parsingParams['items'])
    # self.response.out.write(len(items))
    for item in items: 
      mediaLinks = []
      
      # search for media in description and content
      nodesToCrawl = []
      for crawlTag in parsingParams['crawlTags']:
        nodesToCrawl += item.findall('.//' + crawlTag)
      
      for nodeToCrawl in nodesToCrawl:
        stringToParse = saxutils.unescape(ElementTree.tostring(nodeToCrawl))
        mediaLinks += re.findall(r'<img[^>]*? src=[\'"]([^\'"]+)["\'][^>]*?>', stringToParse, re.IGNORECASE) 
      

      # remove duplicates
      mediaLinks = set(mediaLinks)
      
      # create media items
      for mediaLink in mediaLinks:
        elem = ElementTree.Element(parsingParams['generateParams']['tag'], parsingParams['generateParams']['attrs'])
        elem.attrib[parsingParams['generateParams']['src']] = mediaLink
        elem.attrib['type'] = mimetypes.guess_type(mediaLink)[0]
        if elem.attrib['type'] != None:
          item.append(elem)
    
    self.response.headers['Content-Type'] = 'text/xml' 
    self.response.out.write(ElementTree.tostring(feedTree))
    
    #bla = 2+2
    #children = item.getchildren()
    #for child in children:
    #  self.response.out.write(child.tag)
    #self.response.out.write("ok")
    #for entry in feed.entries:
    #  if entry.has_key('content'):
    #    stringToParse = saxutils.unescape(entry.content[0].value)
    #    imgSrcs = re.findall(r'<img[^>]*? src=[\'"]([^\'"]+)["\'][^>]*?>', stringToParse, re.IGNORECASE) 
    #    for imgSrc in imgSrcs:
    #      self.response.out.write(imgSrc + '\n')
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