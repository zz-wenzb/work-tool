# config/deploy_config.py

DEPLOY_CONFIG = {
    'd1': {
        'service': 'lorry-msp-order-service',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'Pre-to-生产'
    },
    'd2': {
        'service': 'lorry-msp-data-warehouse-service',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd3': {
        'service': 'lorry-msp-wechat-robot',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd4': {
        'service': 'lorry-msp-robot-core',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd5': {
        'service': 'lorry-msp-web',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd6': {
        'service': 'cargo-sync',
        'gitlab_project': 'cargo_platform',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd7': {
        'service': 'cargo-posting',
        'gitlab_project': 'cargo_platform',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd8': {
        'service': 'lorry-msp-job',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd9': {
        'service': 'driver-service',
        'gitlab_project': 'driver-platform',
        'branch': 'test',
        'process': '生产流程'
    },
    'd10': {
        'service': 'driver-search-service',
        'gitlab_project': 'driver-platform',
        'branch': 'test',
        'process': '生产流程'
    },
    'd11': {
        'service': 'oas-mp-order',
        'gitlab_project': 'zhongbao_oas',
        'branch': 'test',
        'process': '生产流程'
    },
    'd12': {
        'service': 'oas-central',
        'gitlab_project': 'zhongbao_oas',
        'branch': 'test',
        'process': '生产流程'
    },
    'd13': {
        'service': 'lorry-msp-marketing',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    },
    'd14': {
        'service': 'tms-central',
        'gitlab_project': 'zhongbao_tms',
        'branch': 'test',
        'process': '生产流程'
    },
    'd15': {
        'service': 'oas-mp-driver',
        'gitlab_project': 'zhongbao_oas',
        'branch': 'test',
        'process': '生产流程'
    },
    'd16': {
        'service': 'lorry-msp-app-driver',
        'gitlab_project': 'lorry_msp_microservice',
        'branch': 'test',
        'process': 'uat卡点生产'
    }
}
