import pyhpi.sahpi

from utils import find_attribute

def find_event_type(event_type):
    return find_attribute(pyhpi.sahpi, event_type, 'SAHPI_ET_')

def find_fumi_access_protocol(proto):
    return find_attribute(pyhpi.sahpi, proto, 'SAHPI_FUMI_PROT_')

def find_fumi_capabilities(capabilities):
    return find_attribute(pyhpi.sahpi, capabilities, 'SAHPI_FUMI_CAP_')

def find_fumi_upgrade_state(state):
    return find_attribute(pyhpi.sahpi, state, 'SAHPI_FUMI_')

def find_fumi_source_status(status):
    return find_attribute(pyhpi.sahpi, status, 'SAHPI_FUMI_SRC_')

def find_dimi_test_service_impact(impact):
    return find_attribute(pyhpi.sahpi, impact, 'SAHPI_DIMITEST_')

def find_dimi_test_capabilities(capabilities):
    return find_attribute(pyhpi.sahpi, capabilities,
            'SAHPI_DIMITEST_CAPABILITY_')

def find_dimi_test_status(status):
    return find_attribute(pyhpi.sahpi, status, 'SAHPI_DIMITEST_STATUS_')

def find_dimi_test_status_error(status):
    return find_attribute(pyhpi.sahpi, status, 'SAHPI_DIMITEST_STATUSERR_')
