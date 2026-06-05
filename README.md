> 禁止🚫使用本项目进行任何形式收费，包括但不限于售卖、付费代装、付费部署、付费托管、付费群/会员/订阅/套餐捆绑、赞助解锁、付费授权或任何变相收费。
>
> 本项目采用 **Non-Commercial Copyleft Public Source License 1.0（类 GPLv3 非商业公共源码许可证）**：可以免费下载、使用、修改和分享；使用、修改或分发后必须继续公开源码；禁止任何形式收费。

# gs_wuwa_daily_wife

GSCore / GsUID 版鸣潮“今日老婆”插件。

## 插件目录

`gs_wuwa_daily_wife`

## 使用方法

固定触发命令：

```text
今日老婆
```

插件禁用 GSCore 强制前缀继承，直接发送 `今日老婆` 即可触发。

触发 `今日老婆` 后，插件会按当天日期、用户 ID 和当前群号固定随机一个结果；同一个用户在不同群会分别固定，不再跨群同步。

默认会随机一个鸣潮角色，然后：

1. 读取角色 ID 对照表；
2. 去 `gsuid_core/data/XutheringWavesUID/custom_role_pile/<数字ID>/`；
3. 随机取一张图片发送。

> 抽群友、`娶群友` 命令和 OneBot HTTP 直抓群成员相关代码已按要求注释停用，代码保留在文件中，后续需要时可以恢复。

如果开启 `DailyWifeMasterUnlimited`，GSCore 主人触发 `今日老婆` 时不会固定当天结果，可以重复随机抽取。

例如随机到“灯灯”，对照表里是 `1504：灯灯`，就会从：

```text
gsuid_core/data/XutheringWavesUID/custom_role_pile/1504/
```

里面取图发送。

## 控制台配置

- `DailyWifeCustomRolePilePath`：自定义图片目录，留空自动查找；
- `DailyWifeRoleMapPath`：自定义角色 ID 对照表，留空使用插件内置；
- `DailyWifeSendText`：是否发送“你今天的老婆是xxx”；
- `DailyWifeShowRoleId`：是否显示角色 ID；
- `DailyWifeTextTemplate`：文字模板；
- `DailyWifeMasterUnlimited`：主人无限抽老婆，默认开启，开启后 GSCore 主人不会固定当天结果。

> `DailyWifeEnableGroupMember`、`DailyWifeGroupMemberProbability`、`DailyWifeOneBotApiUrl`、`DailyWifeOneBotAccessToken` 已随抽群友功能一起注释停用。

## 图片目录要求

每个角色一个数字 ID 文件夹，文件夹里放图片：

```text
custom_role_pile/
├─ 1504/
│  ├─ 1.png
│  └─ 2.jpg
├─ 1203/
│  └─ encore.webp
```

支持：`.jpg`、`.jpeg`、`.png`、`.webp`、`.gif`、`.bmp`。

## 抢老婆

使用 `wl抢老婆 @对方` 或 `wl抢老婆 对方QQ` 可以抢别人的今日老婆。

- 普通用户每天只能抢一次；
- 机器人主人不受次数限制；
- 抢老婆有成功/失败概率；
- 失败提示固定为：`抢老婆失败了，还被对方痛扁了一顿！🤣`；
- 成功后，自己的今日老婆会被替换成对方今天的老婆。
