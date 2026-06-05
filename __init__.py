from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import Plugins, SV
# 抽群友功能已按要求注释停用，保留代码备份时不再需要读取 CoreUser。
# from gsuid_core.utils.database.models import CoreUser

from .daily_wife_config import DailyWifeConfig


Plugins(
    name='gs_wuwa_daily_wife',
    disable_force_prefix=True,
    allow_empty_prefix=True,
)

sv = SV('鸣潮今日老婆')
BASE_DIR = Path(__file__).parent
ROLE_MAP_RE = re.compile(r'^\s*(\d+)\s*[:：]\s*(.+?)\s*$')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}


@dataclass(frozen=True)
class RoleCandidate:
    name: str
    role_ids: tuple[str, ...]
    images: tuple[Path, ...]


@dataclass(frozen=True)
class WifeRecord:
    name: str
    role_ids: tuple[str, ...]
    image: str

    @classmethod
    def from_role(cls, role: RoleCandidate, image: Path) -> 'WifeRecord':
        return cls(role.name, role.role_ids, str(image))

    def to_role(self) -> RoleCandidate:
        return RoleCandidate(self.name, self.role_ids, (Path(self.image),))


"""
抽群友相关代码已按要求注释停用，保留以便之后恢复。

@dataclass(frozen=True)
class MemberCandidate:
    name: str
    user_id: str
    avatar: str
"""


def _cfg(key: str) -> Any:
    return DailyWifeConfig.get_config(key).data


def _configured_path(key: str) -> Path | None:
    raw = str(_cfg(key) or '').strip().strip('"')
    if not raw:
        return None
    return Path(raw).expanduser()


def _resolve_role_map_path() -> Path | None:
    configured = _configured_path('DailyWifeRoleMapPath')
    candidates = [
        configured,
        BASE_DIR / 'role_id_map.txt',
        BASE_DIR.parent / '鸣潮面板id对照角色.txt',
        Path.cwd() / '鸣潮面板id对照角色.txt',
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    return None


def _resolve_role_pile_root() -> Path | None:
    configured = _configured_path('DailyWifeCustomRolePilePath')
    candidates = [configured] if configured else []
    candidates.extend(
        [
            Path.cwd() / 'gsuid_core' / 'data' / 'XutheringWavesUID' / 'custom_role_pile',
            Path.cwd() / 'data' / 'XutheringWavesUID' / 'custom_role_pile',
            BASE_DIR.parent / 'gsuid_core' / 'data' / 'XutheringWavesUID' / 'custom_role_pile',
            BASE_DIR.parent / 'data' / 'XutheringWavesUID' / 'custom_role_pile',
        ]
    )

    try:
        import gsuid_core

        core_root = Path(gsuid_core.__file__).resolve().parents[1]
        candidates.append(core_root / 'data' / 'XutheringWavesUID' / 'custom_role_pile')
    except Exception:
        pass

    for path in candidates:
        if path and path.is_dir():
            return path
    return None


def _load_role_map(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        match = ROLE_MAP_RE.match(line)
        if not match:
            continue
        role_id, role_name = match.groups()
        role_name = role_name.strip()
        if role_name:
            result[role_id] = role_name
    return result


def _role_images(role_dir: Path) -> tuple[Path, ...]:
    images = [
        path
        for path in role_dir.rglob('*')
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return tuple(sorted(images, key=lambda path: str(path).lower()))


def _collect_role_candidates(role_map: dict[str, str], pile_root: Path) -> tuple[RoleCandidate, ...]:
    grouped: dict[str, dict[str, list[Any]]] = {}
    for role_id in sorted(role_map.keys(), key=lambda item: int(item) if item.isdigit() else item):
        role_name = role_map[role_id]
        role_dir = pile_root / role_id
        if not role_dir.is_dir():
            continue
        images = _role_images(role_dir)
        if not images:
            continue
        bucket = grouped.setdefault(role_name, {'role_ids': [], 'images': []})
        bucket['role_ids'].append(role_id)
        bucket['images'].extend(images)

    candidates: list[RoleCandidate] = []
    for role_name, bucket in grouped.items():
        candidates.append(
            RoleCandidate(
                name=role_name,
                role_ids=tuple(str(item) for item in bucket['role_ids']),
                images=tuple(bucket['images']),
            )
        )
    return tuple(sorted(candidates, key=lambda item: item.name))


def _daily_rng(ev: Event, user_id: str | int | None = None) -> random.Random:
    # 按日期、用户和当前会话固定结果；群聊会区分不同群，私聊单独固定。
    group_key = ev.group_id or 'direct'
    target_user_id = ev.user_id if user_id is None else user_id
    seed = f'{date.today().isoformat()}:{target_user_id}:{group_key}'
    return random.Random(seed)


def _is_master(ev: Event) -> bool:
    try:
        masters = core_config.get_config('masters')
    except Exception:
        masters = []
    return str(ev.user_id) in {str(master) for master in masters}


def _event_rng(ev: Event) -> random.Random:
    if bool(_cfg('DailyWifeMasterUnlimited')) and _is_master(ev):
        return random.Random()
    return _daily_rng(ev)



def _wife_data_path() -> Path:
    return BASE_DIR / 'daily_wife_data.json'


def _today_key() -> str:
    return date.today().isoformat()


def _context_key(ev: Event) -> str:
    return f'{ev.bot_id}:{ev.group_id or "direct"}'


def _user_key(ev: Event, user_id: str | int | None = None) -> str:
    return str(ev.user_id if user_id is None else user_id)


def _load_wife_data() -> dict[str, Any]:
    path = _wife_data_path()
    if not path.is_file():
        return {'days': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning(f'[gs_wuwa_daily_wife] 读取数据文件失败，将使用空数据: {exc}')
        return {'days': {}}
    if not isinstance(data, dict):
        return {'days': {}}
    data.setdefault('days', {})
    return data


def _save_wife_data(data: dict[str, Any]) -> None:
    _wife_data_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _get_today_context(data: dict[str, Any], ev: Event) -> dict[str, Any]:
    day = data.setdefault('days', {}).setdefault(_today_key(), {})
    context = day.setdefault(_context_key(ev), {})
    context.setdefault('wives', {})
    context.setdefault('rob_attempts', {})
    return context


def _record_to_dict(record: WifeRecord) -> dict[str, Any]:
    return {'name': record.name, 'role_ids': list(record.role_ids), 'image': record.image}


def _record_from_dict(data: dict[str, Any]) -> WifeRecord | None:
    try:
        record = WifeRecord(
            name=str(data['name']),
            role_ids=tuple(str(item) for item in data.get('role_ids', ())),
            image=str(data['image']),
        )
    except Exception:
        return None
    if not record.name or not record.image or not Path(record.image).is_file():
        return None
    return record


def _get_event_target_user_id(ev: Event) -> str | None:
    at_list = getattr(ev, 'at_list', None)
    if at_list:
        value = next(iter(at_list), None)
        if value:
            return str(value)

    for attr in ('at', 'target_id', 'target_user_id'):
        value = getattr(ev, attr, None)
        if value:
            if isinstance(value, (list, tuple, set)):
                value = next(iter(value), None)
            if value:
                return str(value)

    raw_text = str(getattr(ev, 'text', '') or getattr(ev, 'raw_text', '') or '').strip()
    match = re.search(r'(?:@|qq=|qq:|QQ=|QQ:)?(\d{5,20})', raw_text)
    if match:
        return match.group(1)
    return None


def _rob_success_rate() -> float:
    try:
        value = float(_cfg('DailyWifeRobSuccessRate'))
    except (TypeError, ValueError):
        value = 0.5
    return max(0.0, min(1.0, value))


def _build_rob_success_text(role: RoleCandidate, target_user_id: str) -> str:
    return str(_cfg('DailyWifeRobSuccessTemplate') or '抢老婆成功！你把对方今天的老婆{name}抢过来了！').format(
        name=role.name,
        role_id='/'.join(role.role_ids),
        target=target_user_id,
    )


"""
抽群友功能相关函数已按要求注释停用，保留以便之后恢复。

def _group_member_probability() -> float:
    value = _cfg('DailyWifeGroupMemberProbability')
    try:
        probability = float(value)
    except (TypeError, ValueError):
        probability = 0.1
    return max(0.0, min(1.0, probability))


def _qq_avatar_url(user_id: str) -> str:
    return f'https://q1.qlogo.cn/g?b=qq&s=0&nk={user_id}'


def _valid_member_text(value: Any) -> str:
    text = str(value or '').strip()
    return '' if text in {'', '1', 'None', 'none', 'null'} else text


def _onebot_api_url() -> str:
    return str(_cfg('DailyWifeOneBotApiUrl') or '').strip().rstrip('/')


def _onebot_access_token() -> str:
    return str(_cfg('DailyWifeOneBotAccessToken') or '').strip()


def _member_from_onebot_data(data: dict[str, Any]) -> MemberCandidate | None:
    user_id = _valid_member_text(data.get('user_id'))
    if not user_id:
        return None

    name = (
        _valid_member_text(data.get('card'))
        or _valid_member_text(data.get('nickname'))
        or _valid_member_text(data.get('title'))
        or user_id
    )
    avatar = _valid_member_text(data.get('avatar')) or _qq_avatar_url(user_id)
    return MemberCandidate(name=name, user_id=user_id, avatar=avatar)


async def _load_onebot_group_member_candidates(ev: Event) -> tuple[MemberCandidate, ...]:
    base_url = _onebot_api_url()
    if not base_url or not ev.group_id:
        return ()

    try:
        import httpx
    except Exception as exc:
        logger.warning(f'[gs_wuwa_daily_wife] httpx 不可用，无法直抓群成员: {exc}')
        return ()

    headers: dict[str, str] = {}
    token = _onebot_access_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                f'{base_url}/get_group_member_list',
                json={'group_id': int(ev.group_id)},
                headers=headers,
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning(f'[gs_wuwa_daily_wife] OneBot 直抓群成员失败，将使用缓存: {exc}')
        return ()

    if isinstance(payload, dict):
        status = str(payload.get('status') or '').lower()
        retcode = payload.get('retcode')
        if status and status not in {'ok', 'async'}:
            logger.warning(f'[gs_wuwa_daily_wife] OneBot 返回异常: {payload}')
            return ()
        if retcode not in {None, 0}:
            logger.warning(f'[gs_wuwa_daily_wife] OneBot 返回异常: {payload}')
            return ()
        members_data = payload.get('data') or []
    elif isinstance(payload, list):
        members_data = payload
    else:
        return ()

    candidates: dict[str, MemberCandidate] = {}
    for item in members_data:
        if not isinstance(item, dict):
            continue
        member = _member_from_onebot_data(item)
        if not member or member.user_id == str(ev.bot_self_id or ''):
            continue
        candidates[member.user_id] = member

    return tuple(sorted(candidates.values(), key=lambda item: item.user_id))


async def _load_cached_group_member_candidates(ev: Event) -> tuple[MemberCandidate, ...]:
    if not ev.group_id:
        return ()

    try:
        users = await CoreUser.get_group_all_user(ev.group_id)
    except Exception as exc:
        logger.warning(f'[gs_wuwa_daily_wife] 获取群成员缓存失败: {exc}')
        return ()

    candidates: dict[str, MemberCandidate] = {}
    for user in users or []:
        user_id = _valid_member_text(getattr(user, 'user_id', ''))
        if not user_id or user_id == str(ev.bot_self_id or ''):
            continue
        name = _valid_member_text(getattr(user, 'user_name', '')) or user_id
        avatar = _valid_member_text(getattr(user, 'user_icon', '')) or _qq_avatar_url(user_id)
        candidates[user_id] = MemberCandidate(name=name, user_id=user_id, avatar=avatar)

    return tuple(sorted(candidates.values(), key=lambda item: item.user_id))


async def _load_group_member_candidates(ev: Event) -> tuple[MemberCandidate, ...]:
    direct_members = await _load_onebot_group_member_candidates(ev)
    if direct_members:
        return direct_members
    return await _load_cached_group_member_candidates(ev)


def _select_daily_member(
    rng: random.Random,
    candidates: tuple[MemberCandidate, ...],
) -> MemberCandidate:
    return rng.choice(candidates)


def _build_member_text(member: MemberCandidate) -> str:
    return f'你今天的老婆是{member.name}\nQQ：{member.user_id}'


async def _send_group_member_wife(
    bot: Bot,
    ev: Event,
    rng: random.Random | None = None,
    *,
    force_text: bool = True,
):
    if not ev.group_id:
        return await bot.send('这个命令只能在群聊里使用。')

    members = await _load_group_member_candidates(ev)
    if not members:
        hint = '没有获取到本群成员，暂时娶不到群友。'
        if not _onebot_api_url():
            hint += '\n可在控制台配置 OneBot HTTP API 地址来直抓群成员；未配置时只能使用 GSCore 已记录成员缓存。'
        return await bot.send(hint)

    member = _select_daily_member(rng or _event_rng(ev), members)
    logger.info(
        f'[gs_wuwa_daily_wife] user={ev.user_id} group={ev.group_id} '
        f'member={member.name} qq={member.user_id}'
    )
    if force_text or bool(_cfg('DailyWifeSendText')):
        return await bot.send([
            _build_member_text(member),
            MessageSegment.image(member.avatar),
        ])
    return await bot.send(MessageSegment.image(member.avatar))
"""


def _select_daily_wife(
    ev: Event,
    candidates: tuple[RoleCandidate, ...],
) -> tuple[RoleCandidate, Path]:
    rng = _daily_rng(ev)
    role = rng.choice(candidates)
    return role, rng.choice(role.images)


def _build_text(role: RoleCandidate) -> str:
    lines = [
        str(_cfg('DailyWifeTextTemplate') or '你今天的老婆是{name}').format(
            name=role.name,
            role_id='/'.join(role.role_ids),
        )
    ]
    if bool(_cfg('DailyWifeShowRoleId')):
        lines.append(f'角色ID：{"/".join(role.role_ids)}')
    return '\n'.join(lines)


def _load_candidates() -> tuple[tuple[RoleCandidate, ...] | None, str | None]:
    role_map_path = _resolve_role_map_path()
    if role_map_path is None:
        return None, '没有找到鸣潮角色 ID 对照表。'

    pile_root = _resolve_role_pile_root()
    if pile_root is None:
        return None, '没有找到 custom_role_pile 图片目录。'

    role_map = _load_role_map(role_map_path)
    candidates = _collect_role_candidates(role_map, pile_root)
    if not candidates:
        return None, 'custom_role_pile 里没有找到可用角色图片。'
    return candidates, None


async def _ensure_daily_wife_record(ev: Event, user_id: str | int | None = None) -> WifeRecord | None:
    data = _load_wife_data()
    context = _get_today_context(data, ev)
    key = _user_key(ev, user_id)
    current = context['wives'].get(key)
    if isinstance(current, dict):
        record = _record_from_dict(current)
        if record is not None:
            return record

    candidates, error = _load_candidates()
    if error or not candidates:
        return None

    rng = _daily_rng(ev, key)
    role = rng.choice(candidates)
    image = rng.choice(role.images)
    record = WifeRecord.from_role(role, image)
    context['wives'][key] = _record_to_dict(record)
    _save_wife_data(data)
    return record


async def _send_daily_wife(bot: Bot, ev: Event):
    candidates, error = _load_candidates()
    if error or not candidates:
        return await bot.send(error or '没有找到可用角色。')

    rng = _event_rng(ev)
    """
    抽群友概率分支已按要求注释停用，保留以便之后恢复。
    if bool(_cfg('DailyWifeEnableGroupMember')) and ev.group_id:
        members = await _load_group_member_candidates(ev)
        if members and rng.random() < _group_member_probability():
            return await _send_group_member_wife(bot, ev, rng, force_text=False)
    """

    if bool(_cfg('DailyWifeMasterUnlimited')) and _is_master(ev):
        role = rng.choice(candidates)
        image = rng.choice(role.images)
        record = WifeRecord.from_role(role, image)
    else:
        record = await _ensure_daily_wife_record(ev)
        if record is None:
            return await bot.send('没有找到可用角色。')
        role = record.to_role()
        image = Path(record.image)
    logger.info(
        f'[gs_wuwa_daily_wife] user={ev.user_id} group={ev.group_id or "direct"} '
        f'role={role.name} ids={role.role_ids} image={image}'
    )

    if bool(_cfg('DailyWifeSendText')):
        await bot.send([
            _build_text(role),
            MessageSegment.image(image),
        ])
    else:
        await bot.send(MessageSegment.image(image))




async def _send_rob_wife(bot: Bot, ev: Event):
    target_user_id = _get_event_target_user_id(ev)
    if not target_user_id:
        return await bot.send('要抢谁的老婆？请艾特对方或在命令后面写对方 QQ。')

    robber_id = _user_key(ev)
    if target_user_id == robber_id:
        return await bot.send('自己抢自己的老婆也太奇怪了吧！')

    target_record = await _ensure_daily_wife_record(ev, target_user_id)
    if target_record is None:
        return await bot.send('还没找到可以抢的老婆。')

    data = _load_wife_data()
    context = _get_today_context(data, ev)
    attempts = context.setdefault('rob_attempts', {})
    is_master = _is_master(ev)
    if not is_master and attempts.get(robber_id):
        return await bot.send('今天已经抢过老婆啦，明天再来吧！')

    if not is_master:
        attempts[robber_id] = True

    if random.random() >= _rob_success_rate():
        _save_wife_data(data)
        return await bot.send('抢老婆失败了，还被对方痛扁了一顿！🤣')

    context['wives'][robber_id] = _record_to_dict(target_record)
    _save_wife_data(data)

    role = target_record.to_role()
    image = Path(target_record.image)
    if bool(_cfg('DailyWifeSendText')):
        await bot.send([
            _build_rob_success_text(role, target_user_id),
            MessageSegment.image(image),
        ])
    else:
        await bot.send(_build_rob_success_text(role, target_user_id))


@sv.on_fullmatch('今日老婆', block=True)
async def daily_wife(bot: Bot, ev: Event):
    await _send_daily_wife(bot, ev)


@sv.on_prefix(('抢老婆', '抢今日老婆'), block=True)
async def rob_wife(bot: Bot, ev: Event):
    await _send_rob_wife(bot, ev)


"""
娶群友命令已按要求注释停用，保留以便之后恢复。

@sv.on_fullmatch('娶群友', block=True)
async def group_member_wife(bot: Bot, ev: Event):
    await _send_group_member_wife(bot, ev)
"""
