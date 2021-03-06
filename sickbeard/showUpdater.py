# coding=utf-8
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage. If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

import time
import datetime
import threading

import sickbeard
from sickbeard import logger, ui, db, network_timezones, helpers
from sickbeard.indexers.indexer_config import INDEXER_TVRAGE, INDEXER_TVDB
from sickrage.helper.exceptions import CantRefreshShowException, CantUpdateShowException, ex


class ShowUpdater(object):  # pylint: disable=too-few-public-methods
    def __init__(self):
        self.lock = threading.Lock()
        self.amActive = False

        self.session = helpers.make_session()

    def run(self, force=False):  # pylint: disable=unused-argument, too-many-locals, too-many-branches, too-many-statements

        if self.amActive:
            return

        self.amActive = True

        update_timestamp = time.mktime(datetime.datetime.now().timetuple())
        cache_db_con = db.DBConnection('cache.db')
        result = cache_db_con.select('SELECT `time` FROM lastUpdate WHERE provider = ?', ['theTVDB'])
        if result:
            last_update = long(result[0][0])
        else:
            last_update = long(time.mktime(datetime.datetime.min.timetuple()))
            cache_db_con.action('INSERT INTO lastUpdate (provider, `time`) VALUES (?, ?)', ['theTVDB', last_update])

        network_timezones.update_network_dict()

        url = 'http://thetvdb.com/api/Updates.php?type=series&time={}'.format(last_update)
        data = helpers.getURL(url, session=self.session, returns='text', hooks={'response': self.request_hook})
        if not data:
            logger.log('Could not get the recently updated show data from {}. Retrying later. Url was: {}'.format(sickbeard.indexerApi(INDEXER_TVDB).name, url))
            self.amActive = False
            return

        updated_shows = set()
        try:
            tree = etree.fromstring(data)
            for show in tree.findall('Series'):
                updated_shows.add(int(show.text))
        except SyntaxError:
            update_timestamp = last_update

        pi_list = []
        for cur_show in sickbeard.showList:
            if int(cur_show.indexer) in [INDEXER_TVRAGE]:
                logger.log('Indexer is no longer available for show [{}] '.format(cur_show.name), logger.WARNING)
                continue

            try:
                cur_show.nextEpisode()
                if sickbeard.indexerApi(cur_show.indexer).name == 'theTVDB':
                    if cur_show.indexerid in updated_shows:
                        pi_list.append(sickbeard.showQueueScheduler.action.updateShow(cur_show, True))
            except (CantUpdateShowException, CantRefreshShowException) as error:
                logger.log('Automatic update failed: {}'.format(ex(error)), logger.ERROR)

        ui.ProgressIndicators.setIndicator('dailyUpdate', ui.QueueProgressIndicator('Daily Update', pi_list))

        cache_db_con.action('UPDATE lastUpdate SET `time` = ? WHERE provider=?', [update_timestamp, 'theTVDB'])

        self.amActive = False

    @staticmethod
    def request_hook(response, **kwargs):
        _ = kwargs
        logger.log('{} URL: {} [Status: {}]'.format
                   (response.request.method, response.request.url, response.status_code), logger.DEBUG)

    def __del__(self):
        pass
