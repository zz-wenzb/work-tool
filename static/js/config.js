// ---------- Archery 数据库配置 ----------
// 每个数据库直接映射到对应的实例和完整数据库名
const ARCHERY_DATABASES = [
    // RDS-baoqi
    { id: 'tms', label: 'tms', instance: 'RDS-baoqi', full: 'zhongbao-tms' },
    // RDS-oas
    { id: 'oas', label: 'oas', instance: 'RDS-oas', full: 'zhongbao-oas' },
    // RDS-lorry
    { id: 'lorry', label: 'lorry', instance: 'RDS-lorry', full: 'zhongbao-lorry' },
    { id: 'order', label: 'order', instance: 'RDS-lorry', full: 'zhongbao-lorry-order' },
    { id: 'marketing', label: 'marketing', instance: 'RDS-lorry', full: 'zhongbao-lorry-marketing' },
    { id: 'cargo', label: 'cargo', instance: 'RDS-lorry', full: 'zhongbao-cargo' }
];

// WebSocket 连接地址
const WS_URL = `ws://${window.location.hostname}:8765`;