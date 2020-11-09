#!/usr/bin/env python
# coding: utf8

import requests

"""
This inofficial API is based on the reverse engineering by helvete003
https://github.com/helvete003/bring-api
Thanks for his work!

For information about Bring! please see getbring.com

Everybody feel free to use it, but without any liability or warranty.

Bring! as a Service and Brand is property of Bring! Labs AG
This API was just build because the app is really great and
its users want to include it in any part of their life.
It can be unavailable when ever Bring! Labs decides to publish an official API,
or want's this API to be disabled.

Until then: Thanks to Bring! Labs for their great service!

Made with ❤ and no ☕ in Germany
"""


class BringApi:
    _bringRestURL = "https://api.getbring.com/rest/"
    _translations = None

    class AuthentificationFailed(Exception):
        pass

    def __init__(self, uuid, bringuuid, use_login=False):
        if use_login:
            self.bringUUID, self.bringListUUID = self.login(uuid, bringuuid)
        else:
            self.bringUUID = uuid
            self.bringListUUID = bringuuid
        self.headers = {
            "X-BRING-API-KEY": "cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp",
            "X-BRING-CLIENT": "android",
            "X-BRING-USER-UUID": self.bringUUID,
            "X-BRING-VERSION": "303070050",
            "X-BRING-COUNTRY": "de",
        }
        self.addheaders = {
            "X-BRING-API-KEY": "cof4Nc6D8saplXjE3h3HXqHH8m7VU2i1Gs0g85Sp",
            "X-BRING-CLIENT": "android",
            "X-BRING-USER-UUID": self.bringUUID,
            "X-BRING-VERSION": "303070050",
            "X-BRING-COUNTRY": "de",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

    @classmethod
    def login(cls, email, password):
        try:
            params = {"email": email, "password": password}
            response = requests.get(cls._bringRestURL + "bringlists", params=params)
            response.raise_for_status()
            login = response.json()
            return login["uuid"], login["bringListUUID"]
        except (requests.RequestException, KeyError):
            raise cls.AuthentificationFailed("email password combination not existing")

    # return list of items from current list as well as recent items - translated if requested
    def get_items(self, locale=None) -> dict:
        items = requests.get(
            f"{self._bringRestURL}bringlists/{self.bringListUUID}", headers=self.headers
        ).json()

        if locale:
            transl = BringApi.loadTranslations(locale)
            for item in items["purchase"]:
                item["name"] = transl.get(item["name"]) or item["name"]
            for item in items["recently"]:
                item["name"] = transl.get(item["name"]) or item["name"]
        return items

    # return the details: Name, Image, UUID
    def get_items_detail(self) -> dict:
        return requests.get(
            f"{self._bringRestURL}bringlists/{self.bringListUUID}/details",
            headers=self.headers,
        ).json()

    # add a new item to the current list with a given specification = additional description
    def purchase_item(self, item, specification):
        files = {
            "file": f"&purchase={item}&recently=&specification={specification}&remove=&sender=null"
        }
        requests.put(
            f"{self._bringRestURL}bringlists/{self.bringListUUID}",
            files=files,
            headers=self.addheaders,
        )

    # add/move something to the recent items
    def recent_item(self, item):
        files = {
            "file": f"&purchase=&recently={item}&specification=&remove=&sender=null"
        }
        requests.put(
            f"{self._bringRestURL}bringlists/{self.bringListUUID}",
            files=files,
            headers=self.addheaders,
        )

    # remove an item completely (from recent and purchase)
    def remove_item(self, item):
        files = {
            "file": f"&purchase=&recently=&specification=&remove={item}&sender=null"
        }
        requests.put(
            f"{self._bringRestURL}bringlists/{self.bringListUUID}",
            files=files,
            headers=self.addheaders,
        )

    # search for an item in the list
    # NOT WORKING!
    def search_item(self, search):
        params = {"listUuid": self.bringListUUID, "itemId": search}
        return requests.get(
            f"{self._bringRestURL}bringlistitemdetails/",
            params=params,
            headers=self.headers,
        ).json()

    # // Hidden Icons? Don't know what this is used for
    def load_products(self):
        return requests.get(f"{self._bringRestURL}bringproducts", headers=self.headers)

    # // Found Icons? Don't know what this is used for
    def load_features(self):
        return requests.get(
            f"{self._bringRestURL}bringusers/{self.bringUUID}/features",
            headers=self.headers,
        ).json()

    # load all list infos
    def load_lists(self):
        return requests.get(
            f"{self._bringRestURL}bringusers/{self.bringUUID}/lists",
            headers=self.headers,
        ).json()

    # get list of all users in list ID
    def get_users_from_list(self, listUUID):
        return requests.get(
            f"{self._bringRestURL}bringlists/{listUUID}/users", headers=self.headers
        ).json()

    # get settings from user
    def get_user_settings(self):
        return requests.get(
            f"{self._bringRestURL}bringusersettings/{self.bringUUID}",
            headers=self.headers,
        ).json()

    # Load translation file e. g. via 'de-DE'
    @classmethod
    def loadTranslations(cls, locale):
        if not cls._translations:
            cls._translations = requests.get(
                f"https://web.getbring.com/locale/articles.{locale}.json"
            ).json()
        return cls._translations

    @classmethod
    def translateToCH(cls, item: str, locale) -> str:
        for val, key in cls.loadTranslations(locale).items():
            if key == item:
                return val
        return item

    # Load localized catalag of items
    @classmethod
    def loadCatalog(cls, locale):
        return requests.get(
            f"https://web.getbring.com/locale/catalog.{locale}.json"
        ).json()
