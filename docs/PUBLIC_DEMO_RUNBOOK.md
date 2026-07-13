# BOE Public Demo Runbook

Goal: produce a short, high-quality demonstration showing one shared world edited simultaneously across Unreal, Unity, Godot, and Web Inspector.

## 1. Start BOE Full-Duplex Stack

```bash
python start_duplex_server.py --host 127.0.0.1 --adapters all \
	--live-db world_live.db \
	--web-dev-port 7507 \
	--web-live-port 7508
```

What this gives you:
- Full-duplex adapters for Unreal, Unity, Godot (+ Blender/O3DE/Roblox)
- Central entity synchronization hub with conflict handling
- WebBridge Dev updates on `ws://127.0.0.1:7507/ws`
- WebBridge Live updates on `ws://127.0.0.1:7508/ws`
- Inspector APIs on `http://127.0.0.1:7507/api/inspector` and `http://127.0.0.1:7508/api/inspector`

## 2. Start Web Inspector UI

```bash
cd web
python -m http.server 8080
```

Open:
- `http://127.0.0.1:8080`

## 3. Connect Game Engines

Use each integration guide to connect to its BOE port:
- Unreal -> `127.0.0.1:7100`
- Godot -> `127.0.0.1:7500`
- Unity -> `127.0.0.1:7503`

## 4. Demo Script (Suggested 90 seconds)

1. Scene split screen: Unreal + Unity + Godot + Browser dual inspector (Dev + Live)
2. In Unreal: place block cluster and move one shared entity
3. In Unity: recolor/update adjacent blocks and rotate same entity
4. In Godot: delete a block strip and lock the entity for edit
5. In Unity: attempt stale edit -> show conflict response
6. In Godot: unlock entity
7. In Unreal: apply final movement update
8. In Browser: highlight transaction stream, busiest chunks, dev/live lag blocks

## 5. Capture Guidance

- Record at 1920x1080, 60 FPS
- Keep each engine in a stable camera viewpoint to emphasize synchronization
- Overlay captions only for key events: "Edit", "Conflict", "Resolved", "Synced"
- End with inspector metrics panel showing active writes + entity count

## 6. Quality Checklist

- All 4 clients visibly connected before recording
- Conflict event appears at least once (stale version or lock ownership)
- Final state converges in all clients within a few frames
- Inspector shows non-zero write rate and transaction history
