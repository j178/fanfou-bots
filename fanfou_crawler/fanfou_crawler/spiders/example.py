# -*- coding: utf-8 -*-
import scrapy


class ExampleSpider(scrapy.Spider):
    name = "example"
    allowed_domains = ["fanfou.com"]
    start_urls = ['http://fanfou.com/']

    def parse(self, response):
        pass
