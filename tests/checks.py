"""Shared base for the flow tests.

Each flow runs its steps in order, like a person using the site would, and
reports every failed step by name rather than stopping at the first.
"""
import unittest


class Checks(unittest.TestCase):
    def check(self, name, condition):
        with self.subTest(name):
            self.assertTrue(condition, name)
