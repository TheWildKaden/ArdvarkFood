$root = "AI-Runtime"; $dirs = @(
"models/engine","models/adapters","models/tokenizers","models/configs",
"agent/planner","agent/loop","agent/state","agent/context",
"tools/registry","tools/executor","tools/permissions","tools/builtin",
"tools/filesystem","tools/terminal","tools/python","tools/browser","tools/git","tools/mcp","tools/api",
"multimodal/images","multimodal/audio","multimodal/video",
"memory/short_term","memory/long_term","memory/retrieval",
"storage/history","storage/cache","storage/artifacts","storage/logs",
"api/routes","api/schemas","api/middleware",
"config","tests/unit","tests/integration","scripts","docs"
); New-Item -ItemType Directory -Path $root -Force | Out-Null; foreach ($dir in $dirs) { New-Item -ItemType Directory -Path (Join-Path $root $dir) -Force | Out-Null }; $files = @(
"README.md","PLAN.md",".gitignore",
"config/settings.json",
"models/model_manager.py","models/inference.py",
"agent/agent.py","agent/loop/agent_loop.py","agent/state/state.py","agent/context/context_builder.py","agent/planner/planner.py",
"tools/tool_definition.py","tools/tool_call.py","tools/tool_result.py","tools/registry/registry.py","tools/executor/executor.py","tools/permissions/permission_manager.py",
"multimodal/input_router.py",
"memory/memory_manager.py","memory/retrieval/retriever.py",
"storage/storage_manager.py",
"api/server.py","api/routes/chat.py","api/schemas/messages.py",
"scripts/start.ps1","scripts/setup.ps1",
"tests/unit/test_agent.py","tests/unit/test_tools.py",
"docs/ARCHITECTURE.md","docs/TOOLS.md","docs/MODELS.md",
"requirements.txt"
); foreach ($file in $files) { $path = Join-Path $root $file; if (-not (Test-Path $path)) { New-Item -ItemType File -Path $path -Force | Out-Null } }; Write-Host "AI-Runtime structure created at: $((Resolve-Path $root).Path)" -ForegroundColor Green$root = "AI-Runtime"; $dirs = @(
"models/engine","models/adapters","models/tokenizers","models/configs",
"agent/planner","agent/loop","agent/state","agent/context",
"tools/registry","tools/executor","tools/permissions","tools/builtin",
"tools/filesystem","tools/terminal","tools/python","tools/browser","tools/git","tools/mcp","tools/api",
"multimodal/images","multimodal/audio","multimodal/video",
"memory/short_term","memory/long_term","memory/retrieval",
"storage/history","storage/cache","storage/artifacts","storage/logs",
"api/routes","api/schemas","api/middleware",
"config","tests/unit","tests/integration","scripts","docs"
); New-Item -ItemType Directory -Path $root -Force | Out-Null; foreach ($dir in $dirs) { New-Item -ItemType Directory -Path (Join-Path $root $dir) -Force | Out-Null }; $files = @(
"README.md","PLAN.md",".gitignore",
"config/settings.json",
"models/model_manager.py","models/inference.py",
"agent/agent.py","agent/loop/agent_loop.py","agent/state/state.py","agent/context/context_builder.py","agent/planner/planner.py",
"tools/tool_definition.py","tools/tool_call.py","tools/tool_result.py","tools/registry/registry.py","tools/executor/executor.py","tools/permissions/permission_manager.py",
"multimodal/input_router.py",
"memory/memory_manager.py","memory/retrieval/retriever.py",
"storage/storage_manager.py",
"api/server.py","api/routes/chat.py","api/schemas/messages.py",
"scripts/start.ps1","scripts/setup.ps1",
"tests/unit/test_agent.py","tests/unit/test_tools.py",
"docs/ARCHITECTURE.md","docs/TOOLS.md","docs/MODELS.md",
"requirements.txt"
); foreach ($file in $files) { $path = Join-Path $root $file; if (-not (Test-Path $path)) { New-Item -ItemType File -Path $path -Force | Out-Null } }; Write-Host "AI-Runtime structure created at: $((Resolve-Path $root).Path)" -ForegroundColor Green