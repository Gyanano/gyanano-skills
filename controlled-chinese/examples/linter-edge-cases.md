# linter 测试夹具（有意不合规）

**这不是合格范文，是坏样本。** 每一行都故意写坏，用来确认 `scripts/zh-lint.py` 会报它该报的。跑：

```bash
python3 scripts/zh-lint.py examples/linter-edge-cases.md
```

应当报出这些规则（顺序按行号）：

`vague-time` `vague-scope` `halfwidth-punct` `ban-verb` `range-unmarked` `semicolon`
`empty-verb` `filler` `double-negative` `buzzword` `dangling-conjunction` `anonymous-status`

不该出现的是情态类命中——本文件里的「可能」是内容，不是毛病。

---

## 坏样本

为尽快完成，相关部门要注意: 严禁拖延。

- 提交申请表以及
- 等待审核

工作满 3 天以上不满 1 年的，年休假为 5 日；满 1 年以上不满 10 年的，进行审批。

需要注意的是，这件事不无道理，通过赋能与抓手形成闭环。

已完成，请查收。

## 对照：同一内容的合格写法

处理时限为 3 日，从收到申请之日算起。由内容运营组提交《上线申请单》。

- 提交申请表
- 提交身份证明
- 等待审核

年休假天数按累计工龄计算：

- 满 3 日、不满 1 年：5 日
- 满 1 年、不满 10 年：10 日

内容运营组已完成 6 月报表导出，请查收。

> 注：上面这段「合格写法」是演示用的。本文件整体仍然不是一个合格的制度文本，
> 它只是把同样的信息按规则重排了一遍。
