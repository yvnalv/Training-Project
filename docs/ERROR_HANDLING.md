# Error Handling

VialVision favors **graceful degradation**: a user-facing prediction should survive
failures in non-essential subsystems (DB, camera controls, lookup misses). This
document catalogs the failure modes and how they're handled.

## Principles

1. **Never crash a prediction over a side effect.** Inference results are returned
   even if persistence fails.
2. **Fail fast on startup misconfiguration.** Missing/invalid reference data raises
   a clear error at boot, not deep inside a request.
3. **Degrade, don't guess.** An ambiguous detection count yields *no* MPN, not a
   wrong one.
4. **Log with context.** Warnings/exceptions are logged via the module logger.

## By subsystem

### Inference / MPN
| Situation | Handling |
|---|---|
| `total_tubes != 9` | MPN fields returned as `null`; warning logged; result still returned and saved |
| `detections_to_tubes` gets ≠ 9 | Raises `ValueError` — but only called when count is 9, so it's a guard, not a normal path |
| Pattern not in MPN table | `lookup_mpn` logs a warning and returns `None` values; no exception |
| Font file missing | Falls back to PIL default font (`ImageFont.load_default()`), logs a warning |

### Database (`/predict` persistence)
| Situation | Handling |
|---|---|
| `save_prediction` raises (e.g. disk full, image write error) | Caught in `/predict`; `record_id = None`; full result still returned to the user; exception logged |
| Image file unlink fails during delete/prune | Logged as a warning; the DB row is still removed |
| Corrupt JSON in `tubes`/`detections` columns | `_safe_json` returns `[]`; warning logged |

### Camera
| Situation | Handling |
|---|---|
| picamera2 start fails | Falls back to OpenCV; warning logged |
| No camera opens at all | `start()` raises `RuntimeError` with a platform-specific hint |
| Unsupported Pi control (e.g. AF on CM1/CM2) | Wrapped in try/except; silently ignored |
| `/capture` no frame within timeout | HTTP `503` `{ "error": "Camera not ready — ..." }` |
| `/capture` other error | HTTP `500` `{ "error": "<message>" }`; camera stopped in `finally` |
| Server-mode stream camera fails | `{ "mode": "server", "error": "<message>" }` over WS |

### WebSocket
| Situation | Handling |
|---|---|
| Invalid `resolution` string | Falls back to `640x480`; warning logged |
| Invalid `set_conf` value | Ignored; warning logged |
| Client disconnects | `WebSocketDisconnect` caught; `camera.stop()` in `finally` |
| Unexpected error in loop | Logged; socket closed; camera released |
| Missing `websockets` lib | Uvicorn can't upgrade → `/ws` 404. Install `websockets` (it's in `requirements.txt`) |

### Settings API
| Situation | Handling |
|---|---|
| Invalid JSON body on `PUT /settings` | HTTP `400` `{ "error": "Invalid JSON body." }` |
| Unknown setting keys | Silently ignored (only allowed keys persisted) |
| Device offline (no LAN IP) | `network_ip` is `null` |

### Startup (fail-fast)
| Situation | Handling |
|---|---|
| `mpn_table.csv` missing | `FileNotFoundError` with an actionable message |
| Missing required CSV columns | `ValueError` listing missing/found columns |
| Empty/unreadable CSV | `RuntimeError` |

## HTTP status codes in use

| Code | Where |
|---|---|
| `200` | Normal success (most endpoints, including `/predict` even if DB save failed) |
| `400` | `PUT /settings` invalid JSON |
| `404` | `DELETE /history/{id}` record not found |
| `503` | `GET /capture` no frame within timeout |
| `500` | `GET /capture` unexpected error; (historically) Starlette `TemplateResponse` misuse on `/` — now fixed |

## Notable historical fixes

See [../CHANGELOG.md](../CHANGELOG.md) for full detail:
- Starlette 1.0 `TemplateResponse(request, "index.html")` signature (fixed a 500 on `/`).
- Missing `websockets` dependency (fixed `/ws` 404).
- Pi camera BGR/RGB swap and over-detection (>9 tubes).
