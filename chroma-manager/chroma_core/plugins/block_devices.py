# Copyright (c) 2017 Intel Corporation. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

import json
from logging import DEBUG

import settings
from chroma_core.services import log_register

log = log_register('plugin_runner')
log.setLevel(DEBUG)


def fetch_aggregator():
    import requests

    resp = requests.get(settings.LOCAL_DEVICE_AGGREGATOR_URL)
    payload = resp.text

    return json.loads(payload)


def get_devices(fqdn):
    _data = fetch_aggregator()

    try:
        log.debug('fetching devices for {}'.format(fqdn))
        return _data[fqdn]
    except Exception as e:
        log.error("iml-device-aggregator is not providing expected data, ensure "
                  "iml-device-scanner package is installed and relevant "
                  "services are running on storage servers (%s)" % e)
        return {}
