// ---------- Archery 实例数据库配置 (简化显示) ----------
const ARCHERY_INSTANCES = [
    {
        id: 'baoqi',           // 短命令: /baoqi
        label: 'RDS-baoqi',
        shortLabel: 'baoqi',
        databases: [
            { id: 'tms', label: 'tms', full: 'zhongbao-tms' }
        ]
    },
    {
        id: 'oas',
        label: 'RDS-oas',
        shortLabel: 'oas',
        databases: [
            { id: 'oas', label: 'oas', full: 'zhongbao-oas' }
        ]
    },
    {
        id: 'lorry',
        label: 'RDS-lorry',
        shortLabel: 'lorry',
        databases: [
            { id: 'lorry', label: 'lorry', full: 'zhongbao-lorry' },
            { id: 'lorry-order', label: 'lorry-order', full: 'zhongbao-lorry-order' },
            { id: 'lorry-marketing', label: 'lorry-marketing', full: 'zhongbao-lorry-marketing' },
            { id: 'cargo', label: 'cargo', full: 'zhongbao-cargo' }
        ]
    }
];

// WebSocket 连接地址
const WS_URL = `ws://${window.location.hostname}:8765`;