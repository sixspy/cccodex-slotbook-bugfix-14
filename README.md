# 档期预订

> 遵守 `ops/底座生成前必读_效率与技术栈.md`（≥1000 行像产品）。
> FastAPI + Vue 3 + SQLite；`docker compose up -d --build` 一键起。

## 骨架一句话

档期先占位后确认才进正式册，冲突进候补，确认快照与档期对账。

## 基本信息

| 项 | 值 |
|----|-----|
| 产品名 | 档期预订 |
| 目录 | `09-slotbook` |
| 接口 | http://127.0.0.1:11139 |
| 库 | `data/app.db` |
| 账号 | admin / 123456 |

## 厚度

| 项 | 内容 |
|----|------|
| 后端模块 | db / auth / locks / slots_svc / hold_svc / confirm_svc / waitlist_svc / reconcile_svc / audit_svc / release_svc / transfer_svc |
| 前端视图 | 档期盘 / 占位单 / 候补队列 / 确认入册 / 对账互证 / 审计争用 |
| 空桩 | release（释放重开）、transfer（跨档迁移） |

## 互斥切口候选

- 冲突拒占 vs 进候补自动顶替
- 确认失败整单回滚 vs 影子确认后晋升
- 释放作废正式册 vs 快照强制复检
- 跨档迁移整笔事务 vs 双写影子桥

## 余席口径（BUGFIX-14 已定稿）

余席 = 容量 − 已订 − 待确认（`hold.status='占位中'`）。走甲路径：余席同事务重算并写回
`slots.remaining`，失败则展示余席滚回旧值；余席读与占位写同抢档锁，后到只留争用痕。
细则见 `docs/余席扣待确认说明.md`，禁止前端减一。
