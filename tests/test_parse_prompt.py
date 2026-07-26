"""Tests for parse_prompt module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_prompt import parse_prompt


class TestParsePrompt:
    def test_basic_in_query(self):
        assert parse_prompt("coffee shops in America") == ("coffee shops", "America")

    def test_single_word_category(self):
        assert parse_prompt("dentist in New York") == ("dentist", "New York")

    def test_near_me_removes_suffix(self):
        assert parse_prompt("burger shop near me") == ("burger shop", "")

    def test_no_location(self):
        assert parse_prompt("restaurants") == ("restaurants", "")

    def test_prefix_where_is_the(self):
        assert parse_prompt("Where is the nearest pizza place in Chicago") == (
            "nearest pizza place", "Chicago"
        )

    def test_prefix_find_me(self):
        assert parse_prompt("Find me bakeries in London") == ("bakeries", "London")

    def test_prefix_show_me(self):
        assert parse_prompt("show me gyms in Dubai") == ("gyms", "Dubai")

    def test_prefix_search(self):
        assert parse_prompt("search for hotels in Paris") == ("hotels", "Paris")

    def test_prefix_i_need(self):
        assert parse_prompt("I need mechanics in Berlin") == ("mechanics", "Berlin")

    def test_prefix_looking_for(self):
        assert parse_prompt("looking for cafes in Tokyo") == ("cafes", "Tokyo")

    def test_near_delimiter(self):
        assert parse_prompt("pharmacies near Lahore") == ("pharmacies", "Lahore")

    def test_close_to_me_suffix(self):
        assert parse_prompt("bakeries close to me") == ("bakeries", "")

    def test_in_my_area_suffix(self):
        assert parse_prompt("laundromats in my area") == ("laundromats", "")

    def test_empty_string(self):
        assert parse_prompt("") == ("", "")

    def test_whitespace_only(self):
        assert parse_prompt("   ") == ("", "")

    def test_multi_word_location(self):
        assert parse_prompt("restaurants in New York City") == ("restaurants", "New York City")

    def test_multi_word_category(self):
        assert parse_prompt("coffee shops in San Francisco") == ("coffee shops", "San Francisco")

    def test_complex_realistic_query(self):
        assert parse_prompt("find me the best sushi restaurants in Los Angeles") == (
            "the best sushi restaurants", "Los Angeles"
        )

    def test_nearby_suffix(self):
        assert parse_prompt("gyms nearby") == ("gyms", "")

    def test_around_me_suffix(self):
        assert parse_prompt("dentists around me") == ("dentists", "")
