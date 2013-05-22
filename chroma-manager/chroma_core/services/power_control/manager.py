#
# INTEL CONFIDENTIAL
#
# Copyright 2013 Intel Corporation All Rights Reserved.
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


from collections import defaultdict
import threading
from Queue import Queue

from django.db import transaction

from chroma_core.lib.util import CommandLine, CommandError
from chroma_core.services.log import log_register
from chroma_core.models import PowerControlDevice, PowerControlDeviceOutlet


log = log_register(__name__.split('.')[-1])


class PowerControlManager(CommandLine):
    def __init__(self):
        # Big lock
        self._lock = threading.Lock()
        # Per-device locks
        self._device_locks = defaultdict(threading.Lock)
        self._power_devices = {}
        # Allow us to communicate with our monitoring threads
        self.monitor_task_queue = defaultdict(Queue)

        self._refresh_power_devices()

    def _refresh_power_devices(self):
        # Ensure that we have a fresh view of the DB
        with transaction.commit_manually():
            transaction.commit()

        with self._lock:
            for device in PowerControlDevice.objects.all():
                if device.sockaddr not in self._power_devices:
                    self._power_devices[device.sockaddr] = device

    @property
    def power_devices(self):
        with self._lock:
            return self._power_devices

    def get_monitor_tasks(self, sockaddr):
        with self._lock:
            return self.monitor_task_queue[sockaddr]

    def add_monitor_task(self, sockaddr, task):
        with self._lock:
            self.monitor_task_queue[sockaddr].put(task)

    def register_device(self, device_id):
        device = PowerControlDevice.objects.get(pk = device_id)
        sockaddr = device.sockaddr

        with self._lock:
            self._power_devices[sockaddr] = device

        log.info("Registered device: %s:%s" % sockaddr)

        log.info("Scheduling outlet query for new device: %s:%s" % sockaddr)
        self.add_monitor_task(sockaddr, ('query_device_outlets', {'device_id': device.id}))

    def unregister_device(self, sockaddr):
        sockaddr = tuple(sockaddr)

        with self._lock:
            try:
                del self._power_devices[sockaddr]
                del self._device_locks[sockaddr]
            except KeyError:
                # Never registered with the Manager?
                pass

        log.info("Unregistered device: %s:%s" % sockaddr)

        log.info("Scheduling stop for device monitor: %s:%s" % sockaddr)
        self.add_monitor_task(sockaddr, ('stop', {}))

    def reregister_device(self, device_id):
        # Not happy with this, but we don't have a great way to tell
        # if this was called because some attribute of the PDU was updated
        # or if it was saved due to a relation's update (e.g. an Outlet).
        def _needs_update(old):
            new = PowerControlDevice.objects.get(pk = device_id)

            excludes = ['_state']
            for k, v in new.__dict__.items():
                if k in excludes:
                    continue
                if getattr(old, k, None) != v:
                    return True
            return False

        for sockaddr, old in self._power_devices.items():
            if old.pk == device_id and _needs_update(old):
                self.unregister_device(sockaddr)
                self.register_device(device_id)
                return
            elif old.pk == device_id:
                log.debug("%s:%s was not updated, no need to reregister" % sockaddr)
                return

        raise RuntimeError("Attempt to re-register unregistered device: %s" % device_id)

    def check_device_availability(self, device):
        if not device.all_outlets_known:
            log.info("Scheduling query on %s:%s to resolve unknown outlet states." % device.sockaddr)
            self.add_monitor_task(device.sockaddr, ('query_device_outlets', {'device_id': device.id}))

        with self._device_locks[device.sockaddr]:
            try:
                if device.device_type.max_outlets == 0:
                    for outlet in device.outlets.all():
                        self.try_shell(device.monitor_command(outlet.identifier))
                else:
                    self.try_shell(device.monitor_command())
            except CommandError, e:
                log.error("Device %s did not respond to monitor: %s" % (device, e))
                return False
            return True

    @transaction.commit_on_success
    def toggle_device_outlets(self, toggle_state, outlet_ids):
        state_commands = {
            'on': 'poweron_command',
            'off': 'poweroff_command',
            'reboot': 'powercycle_command'
        }

        for outlet_id in outlet_ids:
            outlet = PowerControlDeviceOutlet.objects.select_related('device').get(pk = outlet_id)
            device = outlet.device
            command = getattr(device, state_commands[toggle_state])

            with self._device_locks[device.sockaddr]:
                try:
                    stdout = self.try_shell(command(outlet.identifier))[1]
                    log.info("Toggled %s:%s -> %s: %s" % (device, outlet.identifier, toggle_state, stdout))
                    if toggle_state in ['on', 'reboot']:
                        outlet.has_power = True
                    else:
                        outlet.has_power = False
                except CommandError, e:
                    log.error("Failed to toggle %s:%s -> %s: %s" % (device, outlet.identifier, toggle_state, e.stderr))
                    outlet.has_power = None
                outlet.save()

    @transaction.commit_on_success
    def query_device_outlets(self, device_id):
        device = PowerControlDevice.objects.get(pk = device_id)

        # Blah. https://bugzilla.redhat.com/show_bug.cgi?id=908455
        # The current assumption is that this query will only be run
        # infrequently, so the iterative interrogation, while annoying,
        # isn't a problem. If it turns out that we need to query PDU
        # outlet state more often, then we'll want to evaluate
        # whether or not we should patch fence_apc.
        #
        # On the other hand, if we're forced to support IPMI, we'll have
        # to query each BMC individually anyhow. We may need to implement
        # some sort of fanout rather than doing it serially.
        with self._device_locks[device.sockaddr]:
            for outlet in device.outlets.order_by("identifier"):
                rc, stdout, stderr = self.shell(device.outlet_query_command(outlet.identifier))

                # These RCs seem to be common across agents.
                # Verified: fence_apc, fence_wti, fence_xvm
                if rc == 0:
                    outlet.has_power = True
                elif rc == 2:
                    outlet.has_power = False
                else:
                    log.error("Unknown outlet state for %s:%s:%s: %s %s %s" % (device.sockaddr + tuple([outlet.identifier, rc, stdout, stderr])))
                    outlet.has_power = None
                log.debug("Learned outlet %s on %s:%s" % (tuple([outlet]) + device.sockaddr))
                outlet.save()
