# config/monitor_config.py

MONITOR_CONFIG = {
    'm1': {
        'service': 'lorry-msp-order-service',
        'process': 'Pre-to-生产'
    },
    'm2': {
        'service': 'lorry-msp-data-warehouse-service',
        'process': 'uat卡点生产'
    },
    'm3': {
        'service': 'lorry-msp-wechat-robot',
        'process': 'uat卡点生产'
    },
    'm4': {
        'service': 'lorry-msp-robot-core',
        'process': 'uat卡点生产'
    },
    'm5': {
        'service': 'lorry-msp-web',
        'process': 'uat卡点生产'
    },
    'm6': {
        'service': 'cargo-sync',
        'process': 'uat卡点生产'
    },
    'm7': {
        'service': 'cargo-posting',
        'process': 'uat卡点生产'
    },
    'm8': {
        'service': 'lorry-msp-job',
        'process': 'uat卡点生产'
    },
    'm9': {
        'service': 'driver-service',
        'process': '生产流程'
    },
    'm10': {
        'service': 'driver-search-service',
        'process': '生产流程'
    },
    'm11': {
        'service': 'oas-mp-order',
        'process': '生产流程'
    },
    'm12': {
        'service': 'oas-central',
        'process': '生产流程'
    },
    'm13': {
        'service': 'lorry-msp-marketing',
        'process': 'uat卡点生产'
    },
    'm14': {
        'service': 'tms-central',
        'process': '生产流程'
    },
    'm15': {
        'service': 'oas-mp-driver',
        'process': '生产流程'
    },
    'm16': {
        'service': 'lorry-msp-app-driver',
        'process': 'uat卡点生产'
    }
}