import React, { useState, useEffect, useRef } from 'react';
import { Settings, Play, Square, Terminal, Save, Folder, Activity, CheckCircle, AlertTriangle, Library } from 'lucide-react';

function App() {
    const [view, setView] = useState('dashboard'); // dashboard | settings
    const [status, setStatus] = useState(false);
    const [logs, setLogs] = useState([]);
    const [config, setConfig] = useState({ library_path: '' });
    const [wsConnected, setWsConnected] = useState(false);
    const logsEndRef = useRef(null);

    // Fetch Status
    const checkStatus = async () => {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            setStatus(data.running);
        } catch (e) {
            console.error("Status check failed", e);
        }
    };

    // Fetch Config
    const fetchConfig = async () => {
        try {
            const res = await fetch('/api/config');
            const data = await res.json();
            setConfig(data);
        } catch (e) {
            console.error("Config fetch failed", e);
        }
    };

    useEffect(() => {
        fetchConfig();
        const interval = setInterval(checkStatus, 2000);
        return () => clearInterval(interval);
    }, []);

    // WebSocket for Logs
    useEffect(() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // When running in dev via proxy, it might be tricky. 
        // Usually host:3000 -> proxy -> backend:8000.
        // If we use relative url '/ws/logs', Vite proxy should handle it if configured with ws: true
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

        let ws = null;

        const connect = () => {
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                setWsConnected(true);
                console.log("WS Connected");
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                // console.log("Log received", data);
                setLogs(prev => [...prev, data]);
            };

            ws.onclose = () => {
                setWsConnected(false);
                setTimeout(connect, 3000);
            };
        };

        connect();

        return () => {
            if (ws) ws.close();
        }
    }, []);

    // Auto-scroll logs
    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    // Helper to add log entries
    const addToLog = (message, level = 'INFO') => {
        setLogs(prev => [...prev, { timestamp: Date.now() / 1000, level, message }]);
    };

    const updateDb = async () => {
        // Direct update without confirm popup (FIXED)
        addToLog("Starting DB update...");
        setLoading(true);
        try {
            const res = await fetch(API_BASE + "/update_db", { method: "POST" });
            const data = await res.json();
            addToLog(data.status);
            // No alert popup here!
        } catch (e) {
            addToLog("Error updating DB: " + e, 'ERROR');
        } finally {
            setLoading(false);
        }
    };

    const handleStart = async () => {
        console.log("Starting scan...");
        try {
            const res = await fetch('/api/start', { method: 'POST' });
            const data = await res.json();
            console.log("Start response:", data);
            setStatus(true);
        } catch (e) {
            console.error("Failed to start scan:", e);
        }
    };

    const handleStop = async () => {
        console.log("Stopping scan...");
        try {
            await fetch('/api/stop', { method: 'POST' });
        } catch (e) {
            console.error("Failed to stop:", e);
        }
    };

    const handleSaveConfig = async () => {
        console.log("Saving config:", config);
        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            if (res.ok) {
                alert("Configuration Saved!");
                console.log("Config saved successfully");
            } else {
                alert("Failed to save configuration");
                console.error("Config save failed", res.status);
            }
        } catch (e) {
            console.error("Config save error:", e);
            alert("Error saving configuration");
        }
    };

    return (
        <div className="flex h-screen text-slate-200 font-sans selection:bg-indigo-500 selection:text-white">
            {/* Sidebar */}
            <div className="w-64 bg-slate-900/50 backdrop-blur-xl border-r border-slate-700/50 flex flex-col p-4 gap-2 shadow-2xl z-10">
                <div className="mb-8 px-2">
                    <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
                        AudioRenamer
                    </h1>
                    <p className="text-xs text-slate-500">Premium Tool v2.0</p>
                </div>

                <NavButton
                    active={view === 'dashboard'}
                    onClick={() => setView('dashboard')}
                    icon={<Activity size={20} />}
                    label="Dashboard"
                />
                <NavButton
                    active={view === 'inventory'}
                    onClick={() => setView('inventory')}
                    icon={<Library size={20} />}
                    label="Inventory"
                />
                <NavButton
                    active={view === 'settings'}
                    onClick={() => setView('settings')}
                    icon={<Settings size={20} />}
                    label="Settings"
                />

                <div className="mt-auto p-4 rounded-xl bg-slate-800/50 border border-slate-700/30">
                    <div className={`flex items-center gap-2 text-sm ${wsConnected ? 'text-emerald-400' : 'text-rose-400'}`}>
                        <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                        {wsConnected ? 'Connected' : 'Disconnected'}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">WebSocket Stream</p>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-auto relative">
                <div className="relative z-10 p-8 max-w-6xl mx-auto">
                    {view === 'dashboard' && (
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Status Card */}
                            <div className="lg:col-span-3 bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6 backdrop-blur-md flex items-center justify-between shadow-lg">
                                <div>
                                    <h2 className="text-lg font-semibold text-white">System Status</h2>
                                    <p className="text-slate-400">Current renaming operation status</p>
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className={`px-4 py-1.5 rounded-full text-sm font-medium border ${status
                                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                                        : 'bg-slate-700/30 border-slate-600/30 text-slate-400'
                                        }`}>
                                        {status ? 'SCANNING RUNNING' : 'IDLE'}
                                    </div>

                                    {!status ? (
                                        <>
                                            <button
                                                onClick={async () => {
                                                    if (confirm("Download large database file (Excel)? This might take a moment.")) {
                                                        const btn = document.activeElement;
                                                        const originalText = btn.innerText;
                                                        btn.innerText = "Requesting...";
                                                        btn.disabled = true;

                                                        try {
                                                            const res = await fetch('/api/update_db', { method: 'POST' });
                                                            if (res.ok) {
                                                                alert("Update started! Please check the 'Live Logs' below for progress.");
                                                            } else {
                                                                alert("Error starting update.");
                                                            }
                                                        } catch (e) {
                                                            alert("Connection Error");
                                                        } finally {
                                                            btn.innerText = originalText;
                                                            btn.disabled = false;
                                                        }
                                                    }
                                                }}
                                                className="px-4 py-2 bg-slate-700/50 hover:bg-slate-700 border border-slate-600/50 text-slate-300 rounded-lg transition-all flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <Activity size={16} />
                                                Update DB
                                            </button>

                                            <button
                                                onClick={handleStart}
                                                className="px-6 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2 font-medium"
                                            >
                                                <Play size={18} fill="currentColor" />
                                                Run Scan
                                            </button>
                                        </>
                                    ) : (
                                        <button
                                            onClick={handleStop}
                                            className="px-6 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg transition-all flex items-center gap-2"
                                        >
                                            <Square size={18} fill="currentColor" />
                                            Stop
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Scheduler Card */}
                            <div className="lg:col-span-3">
                                <SchedulerControl />
                            </div>

                            {/* Log Terminal */}
                            <div className="lg:col-span-3 h-[600px] flex flex-col bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 shadow-2xl font-mono text-sm relative group">
                                <div className="flex items-center gap-2 px-4 py-3 bg-slate-900 border-b border-slate-800">
                                    <Terminal size={14} className="text-slate-500" />
                                    <span className="text-slate-400 text-xs uppercase tracking-wider">Live Logs</span>
                                    <div className="ml-auto flex gap-1.5">
                                        <div className="w-2.5 h-2.5 rounded-full bg-slate-800 border border-slate-700" />
                                        <div className="w-2.5 h-2.5 rounded-full bg-slate-800 border border-slate-700" />
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto p-4 space-y-1 scroll-smooth">
                                    {logs.length === 0 && (
                                        <div className="text-slate-600 italic">Waiting for logs...</div>
                                    )}
                                    {logs.map((log, i) => (
                                        <div key={i} className={`flex gap-3 ${log.level === 'ERROR' ? 'text-rose-400' :
                                            log.level === 'WARNING' ? 'text-amber-400' :
                                                'text-slate-300'
                                            }`}>
                                            <span className="text-slate-600 shrink-0">[{new Date(log.timestamp * 1000).toLocaleTimeString()}]</span>
                                            <span className="break-all">{log.message}</span>
                                        </div>
                                    ))}
                                    <div ref={logsEndRef} />
                                </div>
                            </div>
                        </div>
                    )}

                    {view === 'inventory' && (
                        <InventoryView />
                    )}

                    {view === 'settings' && (
                        <div className="max-w-2xl mx-auto">
                            <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-8 backdrop-blur-md shadow-xl">
                                <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                                    <Settings className="text-indigo-400" /> Configuration
                                </h2>

                                <div className="space-y-6">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-300 mb-2">
                                            Library Path
                                        </label>
                                        <div className="relative">
                                            <Folder className="absolute left-3 top-3 text-slate-500" size={18} />
                                            <input
                                                type="text"
                                                value={config.library_path}
                                                onChange={(e) => setConfig({ ...config, library_path: e.target.value })}
                                                className="w-full bg-slate-900/50 border border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
                                                placeholder="/app/library"
                                            />
                                            <p className="mt-2 text-xs text-slate-500">The absolute path where audiobooks are dropped.</p>
                                        </div>
                                    </div>

                                    <div className="pt-4 border-t border-slate-700/50 flex justify-end">
                                        <button
                                            onClick={handleSaveConfig}
                                            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow-lg shadow-indigo-500/20 font-medium flex items-center gap-2 transition-all active:scale-95"
                                        >
                                            <Save size={18} />
                                            Save Changes
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function NavButton({ active, onClick, icon, label }) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${active
                ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }`}
        >
            {icon}
            <span className="font-medium text-sm">{label}</span>
        </button>
    )
}

function InventoryView() {
    const [books, setBooks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sortConfig, setSortConfig] = useState({ key: 'author', direction: 'asc' });
    const [filter, setFilter] = useState('');

    useEffect(() => {
        fetch('/api/inventory')
            .then(res => res.json())
            .then(data => {
                setBooks(data);
                setLoading(false);
            })
            .catch(err => {
                console.error(err);
                setLoading(false);
            });
    }, []);

    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const sortedBooks = React.useMemo(() => {
        let sortableItems = [...books];

        // Filter first
        if (filter) {
            const f = filter.toLowerCase();
            sortableItems = sortableItems.filter(b =>
                (b.title?.toLowerCase() || '').includes(f) ||
                (b.author?.toLowerCase() || '').includes(f) ||
                (b.ean?.toLowerCase() || '').includes(f)
            );
        }

        if (sortConfig.key !== null) {
            sortableItems.sort((a, b) => {
                let aVal = a[sortConfig.key] || '';
                let bVal = b[sortConfig.key] || '';

                // Special handling for boolean status
                if (typeof aVal === 'boolean') aVal = aVal ? 1 : 0;
                if (typeof bVal === 'boolean') bVal = bVal ? 1 : 0;

                if (typeof aVal === 'string') aVal = aVal.toLowerCase();
                if (typeof bVal === 'string') bVal = bVal.toLowerCase();

                if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    }, [books, sortConfig, filter]);

    const exportInventory = () => {
        window.location.href = '/api/export_inventory';
    };

    if (loading) return <div className="text-slate-400 p-8 text-center">Loading Library...</div>;

    const Th = ({ label, sortKey }) => (
        <th
            className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors select-none overflow-hidden text-ellipsis whitespace-nowrap"
            onClick={() => handleSort(sortKey)}
        >
            <div className="flex items-center gap-1">
                {label}
                {sortConfig.key === sortKey && (
                    <span className="text-indigo-400">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
            </div>
        </th>
    );

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center bg-slate-800/40 p-4 rounded-xl border border-slate-700/50 backdrop-blur-md">
                <input
                    type="text"
                    placeholder="Search Library..."
                    className="bg-slate-900/50 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 w-64"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                />

                <div className="flex gap-4 items-center">
                    <span className="text-sm text-slate-400">Total: <span className="text-white font-mono">{books.length}</span></span>
                    <button
                        onClick={exportInventory}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-all shadow-lg shadow-indigo-500/20"
                    >
                        <Folder size={16} /> Export Excel
                    </button>
                </div>
            </div>

            <div className="bg-slate-900/40 border border-slate-800/50 rounded-xl overflow-hidden backdrop-blur-sm shadow-xl">
                <div className="overflow-x-auto">
                    <table className="w-full table-fixed divide-y divide-slate-800" style={{ tableLayout: 'fixed', width: '100%' }}>
                        <colgroup>
                            <col style={{ width: '60px' }} />
                            <col style={{ width: '140px' }} />
                            <col style={{ width: '25%' }} />
                            <col style={{ width: 'auto' }} />
                            <col style={{ width: '110px' }} />
                            <col style={{ width: '110px' }} />
                        </colgroup>
                        <thead className="bg-slate-900/80">
                            <tr>
                                <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Cover</th>
                                <Th label="EAN" sortKey="ean" />
                                <Th label="Author" sortKey="author" />
                                <Th label="Title" sortKey="title" />
                                <Th label="Date" sortKey="release_date" />
                                <Th label="Status" sortKey="exists" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                            {sortedBooks.slice(0, 100).map((book) => (
                                <tr key={book.ean} className="hover:bg-slate-800/30 transition-colors">
                                    <td className="px-3 py-3 whitespace-nowrap">
                                        <div className="h-10 w-10 rounded bg-slate-800 flex items-center justify-center overflow-hidden">
                                            {book.has_cover && book.relative_cover_path ? (
                                                <img src={book.relative_cover_path} className="h-full w-full object-cover" loading="lazy" />
                                            ) : (
                                                <span className="text-[10px] text-slate-600">No</span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-3 py-3 whitespace-nowrap text-sm font-mono text-slate-400">{book.ean}</td>
                                    <td className="px-3 py-3 whitespace-nowrap text-sm text-slate-200 truncate" title={book.author}>{book.author}</td>
                                    <td className="px-3 py-3 text-sm text-slate-300 truncate" title={book.title}>{book.title}</td>
                                    <td className="px-3 py-3 whitespace-nowrap text-sm text-slate-400">{book.release_date}</td>
                                    <td className="px-3 py-3 whitespace-nowrap">
                                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${book.exists
                                            ? 'bg-emerald-100/10 text-emerald-400 border border-emerald-500/20'
                                            : 'bg-rose-100/10 text-rose-400 border border-rose-500/20'
                                            }`}>
                                            {book.exists ? 'In Library' : 'Missing'}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                            {sortedBooks.length > 100 && (
                                <tr>
                                    <td colspan="6" className="text-center py-4 text-slate-500 text-sm">
                                        Showing first 100 of {sortedBooks.length} results. Use search filter to find specific books.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function SchedulerControl() {
    const [enabled, setEnabled] = useState(false);

    useEffect(() => {
        fetch('/api/scheduler').then(r => r.json()).then(d => setEnabled(d.active));
    }, []);

    const toggle = async () => {
        const newState = !enabled;
        await fetch(`/api/scheduler?enable=${newState}`, { method: 'POST' });
        setEnabled(newState);
    };

    return (
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-4 backdrop-blur-md flex items-center justify-between">
            <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${enabled ? 'bg-indigo-500/20 text-indigo-400' : 'bg-slate-700/50 text-slate-500'}`}>
                    <Activity size={20} />
                </div>
                <div>
                    <h3 className="text-sm font-medium text-slate-200">Auto-Scan Scheduler</h3>
                    <p className="text-xs text-slate-400">{enabled ? 'Active (Every 60 min)' : 'Disabled'}</p>
                </div>
            </div>

            <button
                onClick={toggle}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${enabled ? 'bg-indigo-500' : 'bg-slate-700'}`}
            >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
        </div>
    );
}

export default App;
