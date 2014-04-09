# Copyright 2014 Kontron Europe GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import time

from utils import int_any_base, Logging, PerConnectionStorage

from mapping import *

from pyhpi import Session, EntityPath, FumiRdr, DimiRdr
from pyhpi.utils import event_type_str
from pyhpi.utils import fumi_upgrade_status_str, dimi_test_status_str
from pyhpi.errors import SaHpiError
from pyhpi.sahpi import SAHPI_ET_FUMI, SAHPI_ET_DIMI
from robot.utils.connectioncache import ConnectionCache
from robot.utils import asserts
from robot.utils import secs_to_timestr, timestr_to_secs

class HpiLibrary(Logging, PerConnectionStorage):
    def __init__(self, timeout=10.0, poll_interval=1.0):
        PerConnectionStorage.__init__(self, '_active_session')
        self._cache = ConnectionCache()
        self._active_session = None
        self._timeout = timeout
        self._poll_interval = poll_interval

    def set_timeout(self, timeout):
        """Sets the timeout used in `Wait Until X` keywords to the given value.

        `timeout` is given in Robot Framework's time format
        (e.g. 1 minute 20 seconds) that is explained in the User Guide.

        The old timeout is returned and can be used to restore it later.

        Example.
        | ${tout}= | Set Timeout | 2 minute 30 seconds |
        | Do Something |
        | Set Timeout | ${tout} |
        """

        old = getattr(self, '_timeout', 3.0)
        self._timeout = timestr_to_secs(timeout)
        return secs_to_timestr(old)

    @property
    def _s(self):
        return self._active_session

    def open_hpi_connection(self, host, port=4743, alias=None):
        """Opens an HPI session.

        `host` specifies the hostname or IP address to connect to. `port` is
        the port number the HPI daemon listens on.
        """

        port = int(port)

        self._info('Opening connection to %s:%d' % (host, port))

        os.environ["OPENHPI_DAEMON_HOST"] = str(host)
        os.environ["OPENHPI_DAEMON_PORT"] = str(port)

        session = Session()
        session.open()
        session.attach_event_listener()

        self._active_session = session

        return self._cache.register(session, alias)

    def switch_hpi_connection(self, index_or_alias):
        """Switches between opened HPI session usigg an index or alias.

        The index is got from `Open HPI Connection` keyword, and an alias can
        be given to it.

        Returns the index of previously active connection.
        """

        old_index = self._cache.current_index
        self._active_device = self._cache.switch(index_or_alias)
        return old_index

    def close_hpi_connection(self, loglevel=None):
        """Closes the current HPI session.
        """
        self._active_session.close()

    def close_all_hpi_connections(self):
        """Closes all open HPI sessions and empties the connection cache.

        After this keyword, new indexes got from the `Open HPI Connection`
        keyword are reset to 1.

        This keyword should be used in a test or suite teardown to
        make sure all connections to devices are closed.
        """
        self._active_session = self._cache.close_all()

    def set_entity_path(self, ep):
        """Sets the entity path all further keywords operates on."""

        try:
            ep = EntityPath().from_string(ep)
        except ValueError:
            raise RuntimeError('Invalid entity path "%s"' % ep)
        self._info('Setting entity path to %s' % (ep,))
        self._cp['entity_path'] = ep

    def _selected_resource(self):
        path = self._cp['entity_path']
        res = self._s.get_resources_by_entity_path(path)
        if len(res) != 1:
            raise RuntimeError('More than one resources were retrieved using '
                    'the entity path (%s)' % (path,))
        return res[0]

    def _find_rdr(self, rdr_type, id):
        res = self._selected_resource()
        for rdr in res.rdrs():
            self._debug('Found RDR type "%d" id "%s"' % (rdr.rdr_type,
                rdr.id_string))
            if isinstance(rdr, rdr_type) and rdr.id_string == id:
                self._debug('Found match')
                return rdr
        return None

    def _rdr_should_exist(self, rdr_type, id):
        rdr = self._find_rdr(rdr_type, id)
        if rdr is None:
            raise AssertionError('No FUMI RDR with id "%s" found.' % (id,))
        self._cp['selected_rdr'] = rdr

    def _selected_rdr(self):
        return self._cp['selected_rdr']

    ###
    # General
    ###
    def entity_path_should_exist(self, ep):
        ep = EntityPath().from_string(ep)
        for res in self._s.resources():
            self._debug('%s' % res.rpt)
            if res.rpt.entity_path == ep:
                break
        else:
            raise AssertionError('An RPT with entity path %s does not exist'
                    % (ep,))

    def product_id_of_selected_resource_should_be(self, expected_pid, msg=None,
            values=True):
        expected_pid = int_any_base(expected_pid)
        info = self._selected_resource().rpt.resource_info
        actual_pid = info.product_id
        asserts.fail_unless_equal(expected_pid, actual_pid, msg, values)

    def manufacturer_id_of_selected_resource_should_be(self, expected_mid,
            msg=None, values=True):
        expected_mid = int_any_base(expected_mid)
        info = self._selected_resource().rpt.resource_info
        actual_mid = info.manufacturer_id
        asserts.fail_unless_equal(expected_mid, actual_mid, msg, values)

    ###
    # Events
    ###
    def clear_event_queue(self):
        listener = self._s.event_listener
        while True:
            event = listener.get(timeout=0)
            if event is None:
                return

    def wait_until_event_queue_contains_event_type(self, event_type,
            may_fail=False):
        listener = self._s.event_listener
        event_type = find_event_type(event_type)
        start_time = time.time()
        end_time = start_time + self._timeout
        timeout = end_time - time.time()
        while timeout > 0:
            try:
                event = listener.get(timeout)
                self._debug('Got event %s from queue' %
                        event_type_str(event.event_type))
            except SaHpiError:
                if may_fail:
                    time.sleep(self._poll_interval)
                    continue
                else:
                    raise
            if event.event_type == event_type:
                self._cp['selected_event'] = event
                return

        raise AssertionError('No event with type %s in queue for %s'
                % (event_type_str(event_type), secs_to_timestr(self._timeout)))

    def _selected_event(self):
        return self._cp['selected_event']

    def upgrade_state_of_fumi_event_should_be(self, expected_state, msg=None,
            values=True):
        if self._selected_event().event_type != SAHPI_ET_FUMI:
            raise RuntimeError('Event is not of type FUMI')
        expected_state = find_fumi_upgrade_state(expected_state)
        actual_state = self._selected_event().status
        asserts.fail_unless_equal(expected_state, actual_state, msg, values)

    def test_status_of_dimi_event_should_be(self, expected_status, msg=None,
            values=True):
        if self._selected_event().event_type != SAHPI_ET_DIMI:
            raise RuntimeError('Event is not of type DIMI')
        expected_status = find_dimi_test_status(expected_status)
        actual_status = self._selected_event().run_status
        asserts.fail_unless_equal(expected_status, actual_status, msg, values)

    ###
    # FUMI
    ###
    def set_fumi_number(self, number):
        """Sets the FUMI number for all further FUMI keywords."""
        self._cp['fumi_number'] = number

    def select_logical_bank(self):
        res = self._selected_resource()
        rdr = self._selected_rdr()
        fumi = res.fumi_handler_by_rdr(rdr)
        bank = fumi.logical_bank()
        self._cp['selected_fumi_bank'] = bank

    def select_bank_number(self, number):
        number = int(number)
        res = self._selected_resource()
        rdr = self._selected_rdr()
        fumi = res.fumi_handler_by_rdr(rdr)
        bank = fumi.bank(number)
        self._cp['selected_fumi_bank'] = bank

    def _selected_fumi_bank(self):
        return self._cp['selected_fumi_bank']

    def fumi_rdr_should_exist(self, id):
        """Fails unless the specified FUMI RDR exist.

        `id` is the ID string of the resource descriptor record. If the RDR is
        found, it will be automatically selected.
        """
        self._rdr_should_exist(FumiRdr, id)

    def select_fumi_rdr(self, id):
        """This is just a convenient keyword.

        It does the same as the `FUMI RDR Should Exist` keyword.
        """
        self.fumi_rdr_should_exist(id)

    def fumi_number_of_selected_rdr_should_be(self, expected_num, msg=None,
            values=True):
        res = self._selected_resource()
        rdr = self._selected_rdr()
        expected_num = int(expected_num)
        asserts.fail_unless_equal(expected_num, rdr.fumi_num, msg, values)

    def access_protocol_of_selected_rdr_should_be(self, expected_protocol,
            msg=None, values=True):
        rdr = self._selected_rdr()
        expected_protocol = find_fumi_access_protocol(expected_protocol)
        asserts.fail_unless_equal(expected_protocol, rdr.access_protocol, msg,
                values)

    def capabilities_of_selected_rdr_should_be(self, expected_capabilities,
            msg=None, values=True):
        rdr = self._selected_rdr()
        expected_capabilities = find_fumi_capabilities(expected_capabilities)
        asserts.fail_unless_equal(expected_capabilities, rdr.capability, msg,
                values)

    def number_of_banks_of_selected_rdr_should_be(self, expected_number,
            msg=None, values=True):
        rdr = self._selected_rdr()
        expected_number = int(expected_number)
        asserts.fail_unless_equal(expected_number, rdr.num_banks, msg,
                values)

    def size_of_selected_bank_should_be(self, expected_size, msg=None,
            values=True):
        info = self._selected_fumi_bank().bank_info()
        expected_size = int(expected_size)
        asserts.fail_unless_equal(expected_size, info.size, msg, values)

    def identifier_of_selected_bank_should_be(self, expected_id, msg=None,
            values=True):
        info = self._selected_fumi_bank().bank_info()
        asserts.fail_unless_equal(expected_id, str(info.identifier), msg,
                values)

    def description_of_selected_bank_should_be(self, expected_description,
            msg=None, values=True):
        info = self._selected_fumi_bank().bank_info()
        asserts.fail_unless_equal(expected_description, str(info.description), msg,
                values)

    def datetime_of_selected_bank_should_be(self, expected_datetime, msg=None,
            values=True):
        info = self._selected_fumi_bank().bank_info()
        asserts.fail_unless_equal(expected_datetime, str(info.date_time), msg,
                values)

    def version_of_selected_bank_should_be(self, expected_major,
            expected_minor, expected_aux, msg=None, values=True):
        info = self._selected_fumi_bank().bank_info()
        expected_major = int(expected_major)
        expected_minor = int(expected_minor)
        expected_aux = int(expected_aux)
        asserts.fail_unless_equal(
                (expected_major, expected_minor, expected_aux),
                (info.major_version, info.minor_version, info.aux_version),
                msg, values)

    def set_source(self, uri):
        self._selected_fumi_bank().set_source(uri)

    def start_validation(self):
        self._selected_fumi_bank().start_validation()

    def start_installation(self):
        self._selected_fumi_bank().start_installation()

    def start_rollback(self):
        res = self._selected_resource()
        rdr = self._selected_rdr()
        fumi = res.fumi_handler_by_rdr(rdr)
        fumi.start_rollback()

    def start_activation(self):
        res = self._selected_resource()
        rdr = self._selected_rdr()
        fumi = res.fumi_handler_by_rdr(rdr)
        fumi.start_activation()

    def cancel_upgrade(self):
        self._selected_fumi_bank().cancel()

    def cleanup(self):
        self._selected_fumi_bank().cleanup()

    def upgrade_state_should_be(self, expected_state, msg=None, values=True):
        expected_state = find_fumi_upgrade_state(expected_state)
        state = self._selected_fumi_bank().status()
        asserts.fail_unless_equal(expected_state, state, msg, values)

    def wait_until_upgrade_state_is(self, state, may_fail=False):
        state = find_fumi_upgrade_state(state)
        bank = self._selected_fumi_bank()
        start_time = time.time()
        while time.time() < start_time + self._timeout:
            try:
                _state = bank.status()
            except SaHpiError:
                if may_fail:
                    time.sleep(self._poll_interval)
                    continue
                else:
                    raise
            self._debug('Current upgrade state is %s' %
                    fumi_upgrade_status_str(_state))
            if _state == state:
                return
            time.sleep(self._poll_interval)

        raise AssertionError('Upgrade state %s not reached %s.'
                % (fumi_upgrade_status_str(state),
                    secs_to_timestr(self._timeout)))

    def source_status_should_be(self, expected_status, msg=None, values=True):
        expected_status = find_fumi_source_status(expected_status)
        info = self._selected_fumi_bank().source_info()
        asserts.fail_unless_equal(expected_status, info.source_status.value,
                msg, values)

    ###
    # DIMI
    ###
    def set_dimi_number(self, number):
        """Sets the DIMI number for all further DIMI keywords."""
        self._cp['dimi_number'] = number

    def dimi_rdr_should_exist(self, id):
        """Fails unless the specified DIMI RDR exist.

        A found RDR will be automatically selected. See also `FUMI RDR Should
        Exist` keyword.
        """
        self._rdr_should_exist(DimiRdr, id)

    def select_dimi_rdr(self, id):
        """This is just a convenient keyword.

        It does the same as the `DIMI RDR Should Exist` keyword.
        """
        self.dimi_rdr_should_exist(id)

    def select_test(self, number):
        number = int(number)
        res = self._selected_resource()
        rdr = self._cp['selected_rdr']
        dimi = res.dimi_handler_by_rdr(rdr)
        test = dimi.get_test_by_num(number)
        self._cp['selected_dimi_test'] = test

    def dimi_number_of_selected_rdr_should_be(self, expected_num, msg=None,
            values=True):
        rdr = self._cp['selected_rdr']
        expected_num = int(expected_num)
        asserts.fail_unless_equal(expected_num, rdr.dimi_num, msg, values)

    def name_of_selected_test_should_be(self, expected_name, msg=None,
            values=True):
        test = self._cp['selected_dimi_test']
        asserts.fail_unless_equal(expected_name, test.name, msg, values)

    def service_impact_of_selected_test_should_be(self, expected_impact,
            msg=None, values=True):
        expected_impact = find_dimi_test_service_impact(expected_impact)
        test = self._cp['selected_dimi_test']
        asserts.fail_unless_equal(expected_impact, test.service_impact, msg,
                values)

    def capabilities_of_selected_test_should_be(self, expected_capabilities,
            msg=None, values=True):
        expected_capabilities = \
                find_dimi_test_capabilities(expected_capabilities)
        test = self._cp['selected_dimi_test']
        asserts.fail_unless_equal(expected_capabilities, test.capabilities,
                msg, values)

    def selected_test_should_have_parameter(self, expected_parameter, msg=None,
            values=True):
        test = self._cp['selected_dimi_test']
        parameters = [p.name for p in test.parameters]
        asserts.fail_unless(expected_parameter in parameters, msg)

    def default_value_of_parameter_of_selected_test_should_be(self,
            parameter_name, expected_default_value, msg=None, values=True):
        test = self._cp['selected_dimi_test']
        try:
            parameter = filter(
                    lambda parameter: parameter.name == parameter_name,
                    test.parameters)[0]
        except IndexError:
            raise RuntimeError('Parameter with name "%s" not found.',
                    parameter_name)
        asserts.fail_unless_equal(expected_default_value,
                parameter.default, msg, values)

    def start_test(self, *parameters):
        _parameters = [ p.split('=', 1) for p in parameters ]
        for p in _parameters:
            if len(p) != 2:
                raise RuntimeError('Parameters has to be in form of '
                        '"name=value"')
        test = self._cp['selected_dimi_test']
        test.start(_parameters or None)

    def cancel_test(self):
        test = self._cp['selected_dimi_test']
        test.cancel()

    def test_status_should_be(self, expected_status, msg=None, values=True):
        expected_status = find_dimi_test_status(expected_status)
        test = self._cp['selected_dimi_test']
        status = test.status()[0]
        asserts.fail_unless_equal(expected_status, status, msg, values)

    def wait_until_test_status_is(self, status):
        status = find_dimi_test_status(status)
        test = self._cp['selected_dimi_test']
        start_time = time.time()
        while time.time() < start_time + self._timeout:
            _status = test.status()[0]
            self._debug('Current test status is %s' %
                    dimi_test_status_str(_status))
            if _status == status:
                return
            time.sleep(self._poll_interval)

        raise AssertionError('Test status %s not reached in %s.'
                % (dimi_test_status_str(status),
                    secs_to_timestr(self._timeout)))

    def error_status_of_test_result_should_be(self, expected_status, msg=None,
            values=True):
        expected_status = find_dimi_test_status_error(expected_status)
        test = self._cp['selected_dimi_test']
        result = test.results()
        asserts.fail_unless_equal(expected_status, result.error_code, msg,
                values)

    def test_run_status_of_test_result_should_be(self, expected_status,
            msg=None, values=True):
        expected_status = find_dimi_test_status(expected_status)
        test = self._cp['selected_dimi_test']
        result = test.results()
        asserts.fail_unless_equal(expected_status, result.last_run_status, msg,
                values)

    def result_string_of_test_result_should_be(self, expected_string, msg=None,
            values=True):
        test = self._cp['selected_dimi_test']
        result = test.results()
        asserts.fail_unless_equal(expected_string, result.result, msg, values)
