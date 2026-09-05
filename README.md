# 祁东水务 Home Assistant 集成

非官方 Home Assistant 自定义集成，用于读取 `ccpay.thiscc.com` 上祁东县水务集团微信缴费 H5 返回的水表账户数据。

## 功能

- 通过 Home Assistant **设置 → 设备与服务 → 添加集成** 配置，无需 YAML。
- 只需填写微信水务请求中的 `wid`。
- 自动发现 `wid` 当前绑定的所有户号。
- **以后微信里新绑定户号，无需改配置；下一次数据刷新后自动创建新水表设备和实体。**
- 每个户号独立成为一个 HA 设备。
- 默认每 6 小时刷新。
- 不保存 Cookie / JSESSIONID。
- 获取最近表码、余额、当前待结算数据和最近 10 期历史账单。

## 每个户号创建的实体

- 余额（CNY）
- 累计表码（m³，`water` + `total_increasing`，可加入 HA 能源仪表盘的“用水”）
- 当前待结算水量
- 当前应缴金额
- 最近账单月份
- 最近账单用水量
- 最近账单总费用
- 最近账单水费
- 最近账单污水处理费

`最近账单月份` 实体的属性中还保存最近 10 期原始账单记录。

## 获取 wid

在电脑版微信打开祁东水务缴费页面，用 Fiddler 等工具查看：

`POST https://ccpay.thiscc.com/waterPay/wxpay/getTotalNew.action`

请求表单中的 `param` 解码后类似：

```json
{"wid":"xxxxxxxx","gpsx":0,"gpsy":0}
```

其中 `wid` 即集成需要填写的值。历史账单接口的 `wxid` 使用同一值。

> **安全提醒**：wid 能用于查询绑定的水表信息，应按凭据保管。不要公开贴到 GitHub Issue、日志截图或聊天中。

## 安装方式 A：先手工测试

把：

`custom_components/qidong_water`

整个目录复制到 Home Assistant：

`/config/custom_components/qidong_water`

重启 Home Assistant，然后：

**设置 → 设备与服务 → 添加集成 → 搜索“祁东水务”**

输入 wid 即可。

## 安装方式 B：作为 HACS 自定义仓库

HACS 自定义仓库需要一个公开 GitHub 仓库。上传前先把：

`custom_components/qidong_water/manifest.json`

里的 `YOUR_GITHUB_USERNAME` 替换成你的真实 GitHub 用户名，然后把整个仓库上传到例如：

`https://github.com/<你的用户名>/ha-qidong-water`

之后：

1. HACS → 右上角三点 → 自定义仓库
2. 填入 GitHub 仓库 URL
3. 类型选择“集成”
4. 下载“祁东水务”
5. 重启 Home Assistant
6. 设置 → 设备与服务 → 添加集成 → 祁东水务

## 新增/解绑户号的行为

- **新增户号**：接口 `details` 出现新的 `custcode` 后，集成监听协调器更新并自动添加一整组实体，无需重启。
- **返回顺序变化**：不受影响，所有设备和实体都按 `custcode` 匹配。
- **解绑户号**：原设备/实体会保留在 HA 中，但变为不可用，避免历史统计和实体 ID 突然丢失。

## 能源仪表盘

在：

**设置 → 仪表盘 → 能源 → 用水**

选择对应户号的 **累计表码** 实体。

注意：该数据来自水务公司抄表，并非实时流量；只有水务后台表码更新时累计表码才会变化。

## 已知接口

- 户号/余额/最近表码：`/waterPay/wxpay/getTotalNew.action`
- 历史账单：`/waterPay/search/searchRecord.action`

这是第三方、未公开承诺稳定性的网页接口。如果水务平台更改 URL、参数、风控或要求微信登录态，集成需要同步修改。

## 调试日志

```yaml
logger:
  logs:
    custom_components.qidong_water: debug
```

## 免责声明

本项目与祁东县水务集团、微信、腾讯无官方关联，仅用于读取用户本人有权访问的水表账户数据。
