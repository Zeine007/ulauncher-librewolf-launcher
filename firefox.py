import sqlite3
import tempfile
import shutil
import configparser
import os
import logging
import urllib.parse

logger = logging.getLogger(__name__)


class LibreWolfDatabase:

    def __init__(self):
        #   Results order
        self.order = None

        #   Results number
        self.limit = None

        #   Set database location
        db_location = self.searchPlaces()

        #   Temporary file
        temporary_db_location = tempfile.mktemp()
        shutil.copyfile(db_location, temporary_db_location)

        #   Open LibreWolf database
        self.conn = sqlite3.connect(temporary_db_location)

        #   External functions
        self.conn.create_function("hostname", 1, self.__getHostname)

    def searchPlaces(self):
        #   LibreWolf folder paths (multiple possible locations)
        possible_paths = [
            os.path.join(os.environ["HOME"], ".librewolf"),
            os.path.join(os.environ["HOME"], ".var/app/io.gitlab.librewolf-community/.librewolf"),
            os.path.join(os.environ["HOME"], "snap/librewolf/common/.librewolf")
        ]

        firefox_path = None
        for path in possible_paths:
            if os.path.exists(path):
                firefox_path = path
                break

        if not firefox_path:
            logger.error("LibreWolf profile directory not found")
            return None

        #   LibreWolf profiles configuration file path
        conf_path = os.path.join(firefox_path, "profiles.ini")

        # Debug
        logger.debug("Config path %s" % conf_path)
        if not os.path.exists(conf_path):
            logger.error("LibreWolf profiles.ini not found")
            return None

        #   Profile config parse
        profile = configparser.RawConfigParser()
        profile.read(conf_path)
        
        # Get default profile (LibreWolf might have different section names)
        profiles = [s for s in profile.sections() if s.startswith('Profile')]
        if not profiles:
            logger.error("No profiles found in profiles.ini")
            return None
            
        # Use first profile found
        prof_path = profile.get(profiles[0], "Path")
        if profile.has_option(profiles[0], "IsRelative") and profile.getboolean(profiles[0], "IsRelative"):
            prof_path = os.path.join(firefox_path, prof_path)

        #   Sqlite db directory path
        sql_path = os.path.join(prof_path, "places.sqlite")

        # Debug
        logger.debug("Sql path %s" % sql_path)
        if not os.path.exists(sql_path):
            logger.error("LibreWolf places.sqlite not found")
            return None

        return sql_path

    #   Get hostname from url
    def __getHostname(self, string):
        return urllib.parse.urlsplit(string).netloc

    def search(self, query_str):
        #   Search subquery
        terms = query_str.split(" ")
        term_where = []
        for term in terms:
            term_where.append(
                f'((url LIKE "%{term}%") OR (moz_bookmarks.title LIKE "%{term}%") OR (moz_places.title LIKE "%{term}%"))'
            )

        where = " AND ".join(term_where)

        #    Order subquery
        order_by_dict = {
            "frequency": "frequency",
            "visit": "visit_count",
            "recent": "last_visit_date",
        }
        order_by = order_by_dict.get(self.order, "url")

        query = f"""SELECT 
            url, 
            CASE WHEN moz_bookmarks.title <> '' 
                THEN moz_bookmarks.title
                ELSE moz_places.title 
            END AS label,
            CASE WHEN moz_bookmarks.title <> '' 
                THEN 1
                ELSE 0 
            END AS is_bookmark
            FROM moz_places
                LEFT OUTER JOIN moz_bookmarks ON(moz_bookmarks.fk = moz_places.id)
            WHERE {where}
            ORDER BY is_bookmark DESC, {order_by} DESC
            LIMIT {self.limit};"""

        #   Query execution
        rows = []
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
        except Exception as e:
            logger.error("Error in query (%s) execution: %s" % (query, e))
        return rows

    def close(self):
        self.conn.close()
