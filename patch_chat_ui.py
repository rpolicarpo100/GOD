#!/usr/bin/env python3
"""Patch index.html with chat UI improvements."""
import re
from pathlib import Path

f = Path("index.html")
t = f.read_text(encoding="utf-8")
original = t

# 1. Chat height 400→500
t = t.replace(".chat-b.open{height:400px}", ".chat-b.open{height:500px}")

# 2. Chat header bigger
t = t.replace(
    'padding:5px 16px;cursor:pointer;transition:background .15s;\n}\n.chat-h:hover{background:var(--glass)}\n.chat-h .t{font-size:8px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:600}\n.chat-h .a{font-size:9px;color:var(--dim);transition:transform .25s}',
    'padding:8px 16px;cursor:pointer;transition:background .15s;\n}\n.chat-h:hover{background:var(--glass)}\n.chat-h .t{font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:700}\n.chat-h .a{font-size:10px;color:var(--dim);transition:transform .25s}'
)

# 3. Add chat-tabs CSS + activity-log CSS after .chat-b.open line
tabs_css = """.chat-tabs{display:flex;gap:0;padding:0 16px;border-bottom:1px solid var(--line)}
.chat-tab{padding:8px 16px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;font-weight:500}
.chat-tab:hover{color:var(--text)}
.chat-tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:700}
.chat-tab .badge{display:inline-flex;align-items:center;justify-content:center;min-width:16px;height:16px;border-radius:8px;background:var(--accent);color:#0a0612;font-size:8px;font-weight:700;margin-left:4px;padding:0 4px}
.activity-log{display:none;flex:1;overflow-y:auto;padding:6px 16px;font-size:10px;font-family:var(--mono)}
.activity-log.visible{display:block}
.activity-log .log-entry{display:flex;align-items:flex-start;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)}
.activity-log .log-time{color:var(--dim);font-size:9px;white-space:nowrap;min-width:60px}
.activity-log .log-level{font-size:8px;padding:1px 4px;border-radius:3px;font-weight:600;min-width:40px;text-align:center}
.activity-log .log-level.INFO{background:rgba(108,200,240,.1);color:var(--info)}
.activity-log .log-level.WARN{background:rgba(240,192,80,.1);color:var(--warn)}
.activity-log .log-level.ERROR{background:rgba(232,96,96,.1);color:var(--crit)}
.activity-log .log-msg{color:var(--text);line-height:1.4;word-break:break-word}
"""
# Only insert if not already present
if ".chat-tabs{" not in t:
    t = t.replace(".chat-b.open{height:500px}\n.chat-msgs", ".chat-b.open{height:500px}\n" + tabs_css + ".chat-msgs")

# 4. Chat messages bigger
t = t.replace(
    '.chat-msgs{flex:1;overflow-y:auto;padding:6px 16px;display:flex;flex-direction:column;gap:4px}',
    '.chat-msgs{flex:1;overflow-y:auto;padding:10px 16px;display:flex;flex-direction:column;gap:8px}'
)

# 5. Messages nicer
t = t.replace(
    '.m{max-width:75%;padding:8px 12px;border-radius:12px;font-size:13px;line-height:1.6;white-space:pre-wrap}',
    '.m{max-width:80%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.6;white-space:pre-wrap;position:relative}'
)
t = t.replace(
    '.m.user{align-self:flex-end;background:rgba(139,108,199,.07);border:1px solid rgba(139,108,199,.15)}',
    '.m.user{align-self:flex-end;background:rgba(139,108,199,.1);border:1px solid rgba(139,108,199,.2);border-bottom-right-radius:4px}'
)
t = t.replace(
    '.m.brain{align-self:flex-start;background:var(--glass);border:1px solid var(--line)}',
    '.m.brain{align-self:flex-start;background:var(--glass);border:1px solid var(--line);border-bottom-left-radius:4px}'
)
t = t.replace(
    '.m .w{font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:2px}',
    '.m .w{font-size:8px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:4px;font-weight:600}'
)
t = t.replace(
    '.m .ts{font-size:7px;color:var(--dim);margin-top:2px;opacity:.6}',
    '.m .ts{font-size:8px;color:var(--dim);margin-top:4px;opacity:.6;text-align:right}'
)

# 6. Typing indicator nicer
t = t.replace(
    '.typing{align-self:flex-start;font-size:11px;color:var(--dim);padding:6px 10px;display:flex;gap:3px;align-items:center}',
    '.typing{align-self:flex-start;font-size:12px;color:var(--dim);padding:8px 12px;display:flex;gap:4px;align-items:center;background:var(--glass);border-radius:14px;border:1px solid var(--line)}'
)
t = t.replace('.typing-dot{width:4px;height:4px;', '.typing-dot{width:5px;height:5px;')

# 7. Quick actions bigger
t = t.replace(
    '.chat-q{display:flex;gap:3px;padding:0 16px 5px;overflow-x:auto}',
    '.chat-q{display:flex;gap:6px;padding:6px 16px;overflow-x:auto;flex-wrap:wrap}'
)
t = t.replace(
    '.qb{font-size:8px;padding:2px 7px;border-radius:99px;border:1px solid var(--line);background:transparent;color:var(--dim);white-space:nowrap;flex-shrink:0;transition:all .15s}\n.qb:hover{color:var(--text);border-color:var(--line2)}',
    '.qb{font-size:9px;padding:4px 10px;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--dim);white-space:nowrap;flex-shrink:0;transition:all .15s;font-weight:500}\n.qb:hover{color:var(--text);border-color:var(--accent);background:rgba(139,108,199,.05)}'
)

# 8. Chat input bigger + voice button CSS
t = t.replace(
    '.chat-in{display:flex;gap:5px;padding:6px 16px;border-top:1px solid var(--line)}\n.chat-in input{flex:1;background:var(--bg);border:1px solid var(--line2);border-radius:10px;padding:9px 14px;font-size:13px;outline:none;transition:border-color .2s}\n.chat-in input:focus{border-color:var(--accent)}\n.chat-in button{\n  background:var(--accent);color:#0a0612;border:none;border-radius:10px;\n  padding:9px 16px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:10px;\n  transition:opacity .15s;\n}\n.chat-in button:hover{opacity:.85}',
    '.chat-in{display:flex;gap:8px;padding:10px 16px;border-top:1px solid var(--line);align-items:flex-end}\n.chat-in input[type="text"]{flex:1;background:var(--bg);border:1px solid var(--line2);border-radius:12px;padding:12px 16px;font-size:14px;outline:none;transition:border-color .2s,box-shadow .2s;line-height:1.4}\n.chat-in input[type="text"]:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(139,108,199,.15)}\n.chat-in button[type="submit"]{\n  background:var(--accent);color:#0a0612;border:none;border-radius:12px;\n  padding:12px 20px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:11px;\n  transition:all .15s;min-width:80px;\n}\n.chat-in button[type="submit"]:hover{opacity:.85;transform:translateY(-1px)}\n.chat-in button[type="submit"]:active{transform:translateY(0)}\n.chat-in .voice-btn{\n  background:var(--glass);border:1px solid var(--line);border-radius:12px;\n  padding:12px 14px;font-size:16px;cursor:pointer;transition:all .15s;\n  display:flex;align-items:center;justify-content:center;\n}\n.chat-in .voice-btn:hover{background:var(--line);border-color:var(--line2)}\n.chat-in .voice-btn.recording{background:rgba(232,96,96,.15);border-color:var(--crit);animation:pulse-record 1s infinite}\n@keyframes pulse-record{0%,100%{opacity:1}50%{opacity:.7}}'
)

# 9. HTML: Add voice button + update chat form
t = t.replace(
    '<button type="button" onclick="$(\'file-input\').click()" title="Anexar ficheiro" style="background:var(--glass);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:12px">📎</button>\n          <input id="chat-i" autocomplete="off" placeholder="Fala comigo..."/>',
    '<button type="button" onclick="$(\'file-input\').click()" title="Anexar ficheiro" style="background:var(--glass);border:1px solid var(--line);border-radius:12px;padding:12px 14px;font-size:14px">📎</button>\n          <button type="button" class="voice-btn" id="voice-btn" onclick="toggleVoiceSTT()" title="Falar">🎤</button>\n          <input id="chat-i" type="text" autocomplete="off" placeholder="Escreve ou fala..."/>'
)

# 10. JS: Add toggleVoiceSTT function
if "function toggleVoiceSTT" not in t:
    t = t.replace(
        "function startVoiceSTT(){",
        "function toggleVoiceSTT(){\n  if(sttActive){stopVoiceSTT();}else{startVoiceSTT();}\n}\n\nfunction startVoiceSTT(){"
    )

# 11. JS: Update voice button state in start/stop
t = t.replace(
    "sttRecognition.onstart=()=>{\n    sttActive=true;\n    const el=$('voice-stt-status');",
    "sttRecognition.onstart=()=>{\n    sttActive=true;\n    const btn=$('voice-btn');\n    if(btn){btn.classList.add('recording');btn.textContent='⏹';}\n    const el=$('voice-stt-status');"
)
t = t.replace(
    "function stopVoiceSTT(){\n  sttActive=false;\n  if(sttRecognition){try{sttRecognition.stop();}catch(ex){}}\n  const el=$('voice-stt-status');",
    "function stopVoiceSTT(){\n  sttActive=false;\n  if(sttRecognition){try{sttRecognition.stop();}catch(ex){}}\n  const btn=$('voice-btn');\n  if(btn){btn.classList.remove('recording');btn.textContent='🎤';}\n  const el=$('voice-stt-status');"
)

# 12. JS: Fix activity log rendering
t = t.replace(
    "div.className = 'log-entry';\n  div.innerHTML = '<span class=\"ts\">' + ts + '</span><span class=\"type ' + type + '\">' + type + '</span><span class=\"msg\">' + esc(msg).substring(0, 200) + '</span>';",
    "var levelClass = type.toUpperCase();\n  div.className = 'log-entry';\n  div.innerHTML = '<span class=\"log-time\">' + ts + '</span><span class=\"log-level ' + levelClass + '\">' + esc(type) + '</span><span class=\"log-msg\">' + esc(msg).substring(0, 300) + '</span>';"
)

# Count changes
changes = 0
for i, (a, b) in enumerate(zip(original.split('\n'), t.split('\n'))):
    if a != b:
        changes += 1

if changes > 0:
    f.write_text(t, encoding="utf-8")
    print(f"✅ Patched index.html ({changes} lines changed)")
else:
    print("ℹ️  No changes needed (already patched)")
