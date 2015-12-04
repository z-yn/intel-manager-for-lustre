#
# INTEL CONFIDENTIAL
#
# Copyright 2013-2015 Intel Corporation All Rights Reserved.
#
# The source code contained or described herein and all documents related
# to the source code ("Material") are owned by Intel Corporation or its
# suppliers or licensors. Title to the Material remains with Intel Corporation
# or its suppliers and licensors. The Material contains trade secrets and
# proprietary and confidential information of Intel or its suppliers and
# licensors. The Material is protected by worldwide copyright and trade secret
# laws and treaty provisions. No part of the Material may be used, copied,
# reproduced, modified, published, uploaded, posted, transmitted, distributed,
# or disclosed in any way without Intel's prior express written permission.
#
# No license under any patent, copyright, trade secret or other intellectual
# property right is granted to or conferred upon you by disclosure or delivery
# of the Materials, either expressly, by implication, inducement, estoppel or
# otherwise. Any license under such intellectual property rights must be
# express and approved by Intel in writing.


import os
import platform
import re

SITE_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def calculate_max_clients():
    def physical_ram_mb():
        """
        Calculates the total ram of the system in MB.
        Sets the number of clients to account for 75% of ram on linux and 50% on any other OS.

        :rtype: int
        """
        if platform.system() == 'Linux':
            meminfo = open('/proc/meminfo').read()
            matched = re.search(r'^MemTotal:\s+(\d+)', meminfo)
            if matched:
                return int(matched.groups()[0]) / 1024
        elif platform.system() == 'Darwin':
            meminfo = os.popen("hostinfo").read()
            matched = re.search(r'Primary memory available:\s+(\d+)', meminfo)
            if matched:
                return int(matched.groups()[0]) * 1024
        else:
            raise RuntimeError("Unknown platform type %s" % platform.system())

        raise RuntimeError("Unable to determine physical system ram")

    MB_PER_APACHE_PROCESS = 56
    return int(
        round(physical_ram_mb() / MB_PER_APACHE_PROCESS * (1.5 if platform.system().lower() == 'linux' else 1.25))
    )

_settings = {
    'APP_PATH': {
        'dev': SITE_ROOT,
        'prod': '/usr/share/chroma-manager'
    },
    'REPO_PATH': {
        'prod': '/var/lib/chroma/repo'
    },
    'HTTP_FRONTEND_PORT': {
        'dev': 9000,
        'prod': 80
    },
    'HTTPS_FRONTEND_PORT': {
        'dev': 8000,
        'prod': 443
    },
    'HTTP_AGENT_PORT': {
        'all': 8002
    },
    'HTTP_API_PORT': {
        'all': 8001
    },
    'REALTIME_PORT': {
        'all': 8888
    },
    'SSL_PATH': {
        'dev': SITE_ROOT,
        'prod': '/var/lib/chroma'
    },
    'APACHE_MAX_CLIENTS': {
        'all': calculate_max_clients
    }
}


def get_settings_for(mode):
    """
    Iterates the _settings dictionary, pulling out items that match the given mode.
    This is basically a reduce operation.

    :param mode: The mode to retrieve settings for. Can be 'dev' or 'prod'
    :return: A dictionary of settings for the given type.
    :rtype: dict
    """
    out = {}

    for key, values in _settings.items():
        value = values.get('all') or values.get(mode)

        if callable(value):
            value = value()

        if value is not None:
            out[key] = value

    return out


def get_production_httpd_settings():
    """
    Gets production httpd settings.

    :return: Production Settings
    :rtype: dict
    """
    return get_settings_for('prod')


def get_dev_httpd_settings():
    """
    Gets development httpd settings.

    :return: Development Settings
    :rtype: dict
    """
    return get_settings_for('dev')