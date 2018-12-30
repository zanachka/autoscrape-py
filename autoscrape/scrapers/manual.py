# -*- coding: UTF-8 -*-
import logging
import string
import sys
import re
from itertools import product

from . import BaseScraper
from ..control import Controller
from ..input_parser import InputParser


logger = logging.getLogger('AUTOSCRAPE')


class ManualControlScraper(BaseScraper):
    """
    A Depth-First Search scraper that looks for forms, inputs, and next
    buttons by some manual criteria and iterates accordingly.
    """
    training_classes = [
        "data_pages", "error_pages", "links_to_documents",
        "links_to_search", "search_pages", "crawl_pages",
        "interaction_pages",
    ]

    # TODO: save the path to the matched search form to a file. then
    # upon subsequent loads, we can try that path first and then go
    # from there. this way the manual control scraper can learn from
    # self-exploration based on manual params
    #
    # Another related idea: it would be nice if we had an API that
    # saved data about successful runs and loading/replaying them
    # so users can get familiar with the concepts of self-exploration
    # and self-learning but without having to get the ML concepts.

    def __init__(self, baseurl, loglevel=None, maxdepth=0, formdepth=0,
                 next_match=None, form_match=None,
                 output_data_dir=None, keep_filename=False,
                 disable_style_saving=False,
                 save_screenshots=False, save_graph=False,
                 input=None, leave_host=False,
                 driver="Firefox", remote_hub="http://localhost:4444/wd/hub",
                 link_priority=None, ignore_links=None,
                 form_submit_natural_click=False,
                 form_submit_wait=5, load_images=False, show_browser=False):
        # setup logging, etc
        super(ManualControlScraper, self).setup_logging(loglevel=loglevel)
        # set up web scraper controller
        self.control = Controller(
            leave_host=leave_host, driver=driver, remote_hub=remote_hub,
            form_submit_natural_click=form_submit_natural_click,
            form_submit_wait=int(form_submit_wait),
            load_images=load_images, show_browser=show_browser,
            output_data_dir=output_data_dir,
        )
        self.control.initialize(baseurl)
        # depth of DFS in search of form
        self.maxdepth = int(maxdepth)
        # current depth of iterating through 'next' form buttons
        self.formdepth = int(formdepth)
        # match for link to identify a "next" button
        self.next_match = next_match
        # string to match a form (by element text) we want to scrape
        self.form_match = form_match
        # Where to write training data from crawl
        self.output_data_dir = output_data_dir
        # If this is true, do not use a file hash for the filename
        self.keep_filename = keep_filename
        # Disable saving of stylesheets for web content types
        self.disable_style_saving = disable_style_saving
        # To save screenshots or not (they're large and expensive)
        self.save_screenshots = save_screenshots
        # Whether to save the crawl & interaction traversal graph
        self.save_graph = save_graph
        # string used to match link text in order to sort them higher
        self.link_priority = link_priority
        # string or regex to be used to omit links from clickable
        self.ignore_links = ignore_links
        # attempt a position-based "natural click" over the element
        self.form_submit_natural_click = form_submit_natural_click
        # a period of seconds to force a wait after a submit
        self.form_submit_wait = int(form_submit_wait)
        # a generator, outputting individual form interaction plans
        if input:
            self.input_gen = InputParser(input).generate()
        # if not specified, do nothing with forms
        else:
            self.input_gen = []

    def keep_clicking_next_btns(self, maxdepth=0):
        """
        This looks for "next" buttons, or (in the future) page number
        links, and clicks them until one is not found. This saves the
        pages as it goes.
        """
        logger.debug("*** Entering 'next' iteration routine")
        depth = 0
        while True:
            if self.formdepth and depth > self.formdepth:
                logger.debug("Max 'next' formdepth reached %s" % depth)
                break

            found_next = False
            button_data = self.control.button_vectors()
            n_buttons = len(button_data)
            logger.debug("** 'Next' Iteration Depth %s" % depth)
            logger.debug("Button vectors (%s): %s" % (
                n_buttons, button_data))

            # save the initial landing data page
            self.save_training_page(classname="data_pages")
            self.save_screenshot(classname="data_pages")

            for ix in range(n_buttons):
                button = button_data[ix]
                # TODO: replace this with a ML model to decide whether or
                # not this is a "next" button.
                logger.debug("Checking button: %s" % button)
                if self.next_match.lower() in button.lower():
                    logger.debug("Next button found! Clicking: %s" % ix)
                    depth += 1
                    self.control.select_button(ix, iterating_form=True)
                    # subsequent page loads get saved here
                    self.save_training_page(classname="data_pages")
                    self.save_screenshot(classname="data_pages")

                    found_next = True
                    # don't click any other next buttons
                    break

            if not found_next:
                logger.debug("Next button not found!")
                break

        for _ in range(depth):
            logger.debug("Going back from 'next'...")
            self.control.back()

    def scrape(self, depth=0):
        logger.info("Crawl depth %s" % depth)
        if self.maxdepth and depth > self.maxdepth:
            logger.info("Maximum depth %s reached, returning..." % depth)
            self.control.back()
            return

        self.save_training_page(classname="crawl_pages")
        self.save_screenshot(classname="crawl_pages")
        scraped = False
        form_vectors = self.control.form_vectors(type="text")

        # NOTE: we never get into this loop if self.input_gen is empty
        # this arises when input was not handed to the initializer
        for ix in range(len(form_vectors)):
            # don't bother with looking for forms if we didn't specify
            # th form_match option
            if not self.form_match:
                continue

            form_data = form_vectors[ix]

            # inputs are keyed by form index, purely here for debug purposes
            inputs = self.control.inputs[ix]
            logger.debug("Form: %s Text: %s" % (ix, form_data))
            logger.debug("Inputs: %s" % inputs)

            # TODO: ML model here to determine if this form is
            # scrapeable. Currently this uses strict text match.
            if self.form_match.lower() not in form_data.lower():
                continue

            logger.debug("*** Found an input form!")
            self.save_training_page(classname="search_pages")
            self.save_screenshot(classname="search_pages")

            # TODO: ML model here to determine which inputs require
            # input before submission. The form-selecting classifier
            # above has already made the decision to submit this form,
            # so that is assumed at this point.
            for input_phase in self.input_gen:
                logger.debug("Input plan: %s" % input_phase)
                for single_input in input_phase:
                    input_index = single_input["index"]
                    if single_input["type"] == "input":
                        input_string = single_input["string"]
                        logger.debug("Inputting %s to input %s" % (
                            input_string, ix))
                        self.control.input(ix, input_index, input_string)
                    elif single_input["type"] == "select":
                        input_string = single_input["string"]
                        logger.debug("Selecting option %s in input %s" % (
                            input_string, input_index))
                        self.control.input_select_option(
                            ix, input_index, input_string
                        )
                    elif single_input["type"] == "checkbox":
                        to_check = single_input["action"]
                        logger.debug("%s checkbox input %s" % (
                            "Checking" if to_check else "Unchecking",
                            input_index
                        ))
                        self.control.input_checkbox(
                            ix, input_index, to_check
                        )
                    elif single_input["type"] == "date":
                        input_string = single_input["string"]
                        logger.debug("Setting date to %s in date input %s" % (
                            input_string, ix))
                        self.control.input_date(ix, input_index, input_string)

                self.save_screenshot(classname="interaction_pages")
                self.control.submit(ix)
                logger.debug("Beginning iteration of data pages")
                self.save_screenshot(classname="interaction_pages")
                self.keep_clicking_next_btns(maxdepth=self.formdepth)
                scraped = True
                self.control.back()

            logger.debug("Completed iteration!")
            # Only scrape a single form, due to explicit, single
            # match configuration option

            if scraped:
                logger.debug("Scrape complete! Exiting.")
                return

        # TODO: this will be replaced by a ML algorith to sort links by those
        # most likely to be fruitful
        links = self.control.clickable
        link_vectors = self.control.link_vectors()
        link_zip = list(zip(range(len(link_vectors)),link_vectors))
        if self.link_priority:
            logger.debug("Sorting by link priority: %s" % self.link_priority)
            link_zip.sort(
                key=lambda x: not re.findall(self.link_priority, x[1])
            )
        if self.ignore_links:
            logger.debug("Ignoring links matching: %s" % self.ignore_links)
            link_zip = filter(
                lambda x: not re.findall(self.ignore_links, x[1]),
                link_zip
            )
        for ix, text in link_zip:
            if self.maxdepth and depth == self.maxdepth:
                logger.debug("At maximum depth: %s, skipping links." % depth)
                break

            logger.debug("Attempting to click link text: %s" % text)
            if self.control.select_link(ix):
                logger.info("Link clicked: %s" % text)
                self.scrape(depth=depth + 1)
            else:
                logger.debug("Link downloaded or click failed: %s" % text)

        logger.debug("Searching forms and links on page complete")
        self.control.back()

    def run(self, *args, **kwargs):
        try:
            self.scrape(*args, **kwargs)
        except Exception as e:
            self.control.scraper.driver.quit()
            if self.output_data_dir and self.save_graph:
                self.save_scraper_graph()
            raise e

