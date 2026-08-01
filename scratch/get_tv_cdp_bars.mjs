import http from 'http';

async function getCDPPage() {
    return new Promise((resolve) => {
        http.get('http://127.0.0.1:9222/json', (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const pages = JSON.parse(data);
                    const tvPage = pages.find(p => (p.url && p.url.includes('tradingview.com')) || (p.title && p.title.includes('TradingView')));
                    resolve(tvPage);
                } catch (e) {
                    resolve(null);
                }
            });
        }).on('error', () => resolve(null));
    });
}

async function evalInCDP(wsUrl, script) {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        let id = 1;
        ws.onopen = () => {
            ws.send(JSON.stringify({
                id: id++,
                method: 'Runtime.evaluate',
                params: { expression: script, returnByValue: true }
            }));
        };
        ws.onmessage = (event) => {
            const res = JSON.parse(event.data);
            if (res.id === 1) {
                ws.close();
                resolve(res.result?.result?.value);
            }
        };
        ws.onerror = reject;
    });
}

async function main() {
    const page = await getCDPPage();
    if (!page) {
        console.log("❌ TradingView CDP Port 9222 not reachable. Launch TradingView debug instance first.");
        return;
    }
    
    console.log("✅ Connected to TradingView CDP Page:", page.title);
    const extractScript = `
    (() => {
        try {
            const chart = window.TradingView?.activeChart?.() || window.tvWidget?.activeChart?.();
            if (!chart) return { error: "No active chart found" };
            
            const symbol = chart.symbol();
            const res = chart.resolution();
            return { symbol, res };
        } catch (e) {
            return { error: e.toString() };
        }
    })()
    `;
    
    const res = await evalInCDP(page.webSocketDebuggerUrl, extractScript);
    console.log("Chart State:", res);
}

main();
