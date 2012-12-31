---
layout: default
title: Feed-buster
description: Web service for injecting MediaRSS tags into RSS/ATOM feeds
github_url: https://github.com/izuzak/feedbuster
ga_tracking: UA-5997170-3

---

Overview
--------

Feed-buster is a service that enables better RSS/ATOM feed media importing into [FriendFeed](http://friendfeed.com/). Here is the result of using Feed-buster when importing feeds into FriendFeed:

<img src="https://raw.github.com/izuzak/feedbuster/master/src/static/fbDemoPic.PNG" />

Feed-buster is actually a collection of [AppEngine](https://developers.google.com/appengine/) services for remixing RSS and ATOM feeds. Currently, the only service is MediaInjection which injects media enclosure links into feed posts based on media present in the item description and content

Media injection
---------------

Media enclosures are special RSS/ATOM tags that identify rich media content in feed posts. The Media injection service automatically inserts media enclosure tags into RSS/ATOM feeds that do not have them. The service crawls feed posts for rich media, generates and inserts media tags back into the feed for each post, and outputs the resulting feed.

Why do this? Some feed-based applications, like FriendFeed, generate their UIs based on media present in feeds. These applications don't crawl the content of feed posts for media items, rather just look for special media tags that identify this media. Therefore, if no media tags are present, the UI will not contain any rich media like images and videos, and this causes bad user experience.

Feed-buster generates media enclosure tags based on the Media RSS standard module, which is used by FriendFeed. See the [RSS 2.0 specification](http://www.rssboard.org/rss-specification#ltenclosuregtSubelementOfLtitemgt) and [Media RSS module definition](http://search.yahoo.com/mrss/) for a detailed explanation of media enclosures and Media RSS extension. Currently, feed-buster crawls images, mp3 audio links, youtube embedded videos and vimeo embedded videos. Support for other media is on the way.

### Service API

Media injection is a simple HTTP service: you pass it a feed URL in a GET request URL parameter, and it returns the modified feed as the result. Replace `FEED_URL` with your RSS or ATOM feed URL in the following:

    http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=FEED_URL

Example: for the feed `http://feeds.laughingsquid.com/laughingsquid` the service call would be `http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=http://feeds.laughingsquid.com/laughingsquid`.

Optional URL parameters:

 * *scrape media from feed website* - some feeds do not contain media which is present in the web version of the posts. In such cases, use this option to force feed-buster to try and scrape the media from the feed website. To use this option, append `&webScrape=1` to the end of the URL - `http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=FEED_URL&webScrape=1`.
 * *insert description element* - some feeds do not contain a description element which FriendFeed uses when importing custom RSS/ATOM feeds to generate a snippet which describes the imported posts. In such cases, use this option to force feed-buster to try and generate the description element of maximum length `LENGTH` from the content element. To use this option, append `&getDescription=_LENGTH_` to the end of the URL - `http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=FEED_URL&getDescription=4000`.

### URL-builder form

<script type="text/javascript">
  function generate() {
    _gaq.push(['_trackEvent', 'URL builder', 'createURL'])

    var inputUrl = document.getElementById("inputUrl").value;
    var outputUrl = "http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=" + inputUrl;
    if (document.getElementById("webScrape2").checked) {
      outputUrl += "&webScrape=1"
    }
    if (document.getElementById("getDescription2").checked) {
      outputUrl += "&getDescription=" + document.getElementById("maxDescription").value
    }
    document.getElementById("outputUrl").value = outputUrl;
  }
</script>
<div id="wikicontent"> <p>
<b><label for="inputUrl">Your RSS/ATOM feed URL:</label></b>
<input style="width:300px" name="inputUrl" id="inputUrl" type="text" value=""/>

</p><p><label for="webScrape1"><b>Scrape media from website</b>:</label>
<label for="webScrape1">No:</label><input name="webScrape" id="webScrape1" type="radio" value="No" checked="checked"/>
<label for="webScrape2">Yes:</label><input name="webScrape" id="webScrape2" type="radio" value="Yes"/>

</p><p><label style="width:640px;" for="getDescription1"><b>Create description element</b>:</label>
<label for="getDescription1">No:</label><input name="getDescription" id="getDescription1" type="radio" value="No" checked="checked"/>
<label for="getDescription2">Yes:</label><input name="getDescription" id="getDescription2" type="radio" value="Yes"/>
<label for="maxDescription">Max. length:</label> <input style="width:100px" name="maxDescription" id="maxDescription" type="text" value=""/>

</p><p><button style="margin-left: 60px;" name="genBtn" id="genBtn" onclick="generate();">Generate feed-buster URL</button>

</p><p><b><label for="outputUrl">Feed-buster feed URL:</label></b>
<input style="width:300px" name="outputUrl" id="outputUrl" type="text" value="">
</p>
<p align="justify">Copy/paste the output URL and try the new feed out on the <a href="http://friendfeed.com/api/feedtest" target="_blank">FriendFeed feedtest page</a>!
</p>
</div>

Credits
-------

Feed-buster is developed by [Ivan Zuzak](http://ivanzuzak.info) [&lt;izuzak@gmail.com&gt;](mailto:izuzak@gmail.com).

Libraries and services used:

  * [py-dom-xpath](http://code.google.com/p/py-dom-xpath/) - library for XPath support
  * [IMG2JSON](http://img2json.appspot.com/) - AppEngine service for retrieving image metadata
  * [Beautiful Soup](http://www.crummy.com/software/BeautifulSoup/) - library for scraping feeds

License
-------

Licensed under the [Apache 2.0 License](https://github.com/izuzak/feedbuster/blob/master/LICENSE.md).
