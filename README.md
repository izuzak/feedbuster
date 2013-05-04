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

A simple URL builder for feed-buster is available at: [http://izuzak.github.com/feedbuster](http://izuzak.github.com/feedbuster).

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

[![gaugestracking alpha](https://secure.gaug.es/track.gif?h[site_id]=5163cdab613f5d50c70000ae&h[resource]=http%3A%2F%2Fgithub.com%2Fizuzak%2Ffeedbuster&h[title]=feedbuster%20%28GitHub%29&h[unique]=1&h[unique_hour]=1&h[unique_day]=1&h[unique_month]=1&h[unique_year]=1 "ivanzuzak.info")](http://ivanzuzak.info/)
