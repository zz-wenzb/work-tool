// ---------- 全局变量 ----------
let ws;
const messagesDiv = document.getElementById('messages');
const errorDiv = document.getElementById('error');
const joinBox = document.getElementById('join-box');
const chatBox = document.getElementById('chat-box');
const deployListContainer = document.getElementById('deploy-list-container');
let windowAllDeployItems = [];

// ---------- 辅助函数 ----------
function showError(msg) {
    errorDiv.textContent = msg;
    setTimeout(() => {
        errorDiv.textContent = '';
    }, 5000);
}

function showJoin() {
    joinBox.classList.add('active');
    chatBox.classList.remove('active');
}

function showChat() {
    joinBox.classList.remove('active');
    chatBox.classList.add('active');
    document.getElementById('message').focus();
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function fillCmd(cmd) {
    const input = document.getElementById('message');
    input.value = cmd + " ";
    input.focus();
}

// ---------- 创建消息元素 ----------
function createMessageElement(type, nickname, content, time, isOwn = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'msg';

    if (isOwn) {
        msgDiv.classList.add('own');
    }

    if (type === 'system') {
        msgDiv.classList.add('system');
        msgDiv.textContent = content;
        return msgDiv;
    }

    if (type === 'chat') {
        msgDiv.classList.add('chat');

        // 判断是否为命令（以 / 开头）
        const isCommand = content.startsWith('/');

        // 构建消息内容
        let bodyHtml = content.replace(/\n/g, '<br>');
        if (isCommand) {
            // 命令用蓝色高亮
            bodyHtml = `<span style="color:#2563eb;font-weight:600;font-family:'JetBrains Mono','Fira Code',monospace;">${content}</span>`;
        }

        // 构建完整的消息 HTML
        msgDiv.innerHTML = `
            <span class="msg-nickname">${nickname}</span>
            <span class="msg-time">${time}</span>
            <span class="msg-body">${bodyHtml}</span>
        `;
    }

    return msgDiv;
}

// ---------- 渲染 Archery 实例列表 ----------
function renderArcheryInstances() {
    const container = document.getElementById('archery-instance-list');
    container.innerHTML = '';

    const groups = {};
    ARCHERY_DATABASES.forEach(db => {
        if (!groups[db.instance]) {
            groups[db.instance] = [];
        }
        groups[db.instance].push(db);
    });

    Object.keys(groups).forEach(instance => {
        const dbs = groups[instance];

        const instanceLi = document.createElement('li');
        instanceLi.className = 'archery-instance-title';
        instanceLi.textContent = `📊 ${instance}`;
        container.appendChild(instanceLi);

        dbs.forEach(db => {
            const li = document.createElement('li');
            li.className = 'archery-db-item';

            const code = document.createElement('code');
            const cmd = `/${db.id}`;
            code.textContent = cmd;
            code.onclick = () => fillCmd(cmd);
            code.title = `点击填入 ${cmd}`;

            const desc = document.createElement('span');
            desc.className = 'db-desc';
            desc.textContent = `→ ${db.full}`;

            li.appendChild(code);
            li.appendChild(desc);
            container.appendChild(li);
        });
    });
}

// ---------- 渲染部署列表 ----------
function renderDeployList(projects, commandsMap) {
    windowAllDeployItems = [];
    deployListContainer.innerHTML = '';

    if (!commandsMap || Object.keys(commandsMap).length === 0) {
        deployListContainer.innerHTML = '<li class="loading-text">暂无项目数据</li>';
        return;
    }

    const ul = document.createElement('ul');

    const sortedCommands = Object.entries(commandsMap).sort((a, b) => {
        const numA = parseInt(a[0].replace('/d', ''));
        const numB = parseInt(b[0].replace('/d', ''));
        return numA - numB;
    });

    sortedCommands.forEach(([cmd, cfg]) => {
        const serviceName = typeof cfg === 'object' ? (cfg.service || '未知服务') : cfg;
        const branchInfo = typeof cfg === 'object' && cfg.branch ? `(${cfg.branch})` : '';

        const li = document.createElement('li');
        li.innerHTML = `<code>${cmd}</code> ${serviceName} <small style="color:#64748b;font-size:10px">${branchInfo}</small>`;
        li.title = `点击复制 ${cmd} 部署 ${serviceName}`;
        li.onclick = () => fillCmd(cmd);

        ul.appendChild(li);

        windowAllDeployItems.push({
            cmd: cmd,
            service: serviceName,
            branch: branchInfo,
            element: li
        });
    });

    deployListContainer.appendChild(ul);
    filterDeployList(document.getElementById('deploy-search').value);
}

function filterDeployList(keyword) {
    const ul = deployListContainer.querySelector('ul');
    if (!ul) return;

    const term = keyword.toLowerCase().trim();
    let visibleCount = 0;
    const items = ul.querySelectorAll('li');

    items.forEach(li => {
        const text = li.textContent.toLowerCase();
        if (term === '' || text.includes(term)) {
            li.style.display = '';
            visibleCount++;
        } else {
            li.style.display = 'none';
        }
    });

    let noResultMsg = ul.querySelector('.no-result');
    if (visibleCount === 0) {
        if (!noResultMsg) {
            noResultMsg = document.createElement('li');
            noResultMsg.className = 'no-result';
            noResultMsg.textContent = '🔎 未找到匹配的项目';
            ul.appendChild(noResultMsg);
        }
    } else {
        if (noResultMsg) noResultMsg.remove();
    }
}

// ---------- WebSocket 连接 ----------
function joinChat() {
    const nickInput = document.getElementById('nickname');
    const nick = nickInput.value.trim();

    if (!nick || nick.length < 2) {
        showError("昵称至少需要2个字符");
        nickInput.focus();
        return;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
    }

    console.log("[WS] 连接至:", WS_URL);
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log("[WS] 已连接，发送加入请求");
        ws.send(JSON.stringify({type: "join", nickname: nick}));
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log("[收到]", data);

            if (data.type === 'project_list') {
                renderDeployList(data.data, data.dynamic_commands);
                return;
            }

            if (data.type !== 'error') {
                showChat();
            }

            if (data.type === 'system') {
                const msgDiv = createMessageElement('system', '', data.content, data.time);
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            } else if (data.type === 'chat') {
                const myNick = document.getElementById('nickname').value.trim();
                const isOwn = data.nickname === myNick;

                // 去重
                const lastMsg = messagesDiv.lastElementChild;
                if (isOwn && lastMsg && lastMsg.dataset.content === data.content) {
                    return;
                }

                const msgDiv = createMessageElement('chat', data.nickname, data.content, data.time, isOwn);
                if (isOwn) {
                    msgDiv.dataset.content = data.content;
                }
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            } else if (data.type === 'error') {
                showError(data.content);
                ws.close();
                return;
            }
        } catch (e) {
            console.error("消息解析失败:", e);
        }
    };

    ws.onclose = (event) => {
        console.log("[WS] 关闭", event.code, event.reason);
        if (event.code !== 1000) {
            showError("连接断开：" + (event.reason || "未知原因"));
        }
        showJoin();
    };

    ws.onerror = (err) => {
        console.error("[WS] 错误", err);
        showError("连接发生错误，请刷新页面重试");
        showJoin();
    };
}

// ---------- 发送消息 ----------
function sendMessage() {
    const input = document.getElementById('message');
    const content = input.value.trim();
    if (!content) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
        const nickname = document.getElementById('nickname').value.trim() || '我';
        const now = new Date();
        const timeStr = now.toTimeString().slice(0, 8);

        // 立即显示
        const msgDiv = createMessageElement('chat', nickname, content, timeStr, true);
        msgDiv.dataset.content = content;
        messagesDiv.appendChild(msgDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;

        ws.send(JSON.stringify({type: "chat", content: content}));
        input.value = '';
    } else {
        showError("未连接到服务器");
    }
}

// ---------- 键盘事件 ----------
document.getElementById('nickname').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') joinChat();
});

document.getElementById('message').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// 启动时聚焦 + 渲染 Archery 实例列表
window.onload = () => {
    document.getElementById('nickname').focus();
    renderArcheryInstances();
};