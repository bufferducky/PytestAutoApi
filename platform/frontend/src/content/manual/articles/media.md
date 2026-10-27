# 测试媒体manifest与校验

manifest是受控测试文件的资料卡，不是上传客户录音入口。

## 文件先准备好，再登记 {#manifest-example}

文件必须已在worker可用的Files/test-media受控目录。示例形状如下，hash和大小必须从实际合成文件计算，不能复制占位提交：

```json
{
  "name":"合成测试语音",
  "path":"Files/test-media/example.wav",
  "sha256":"<实际64位SHA256>",
  "byte_size":32044,
  "duration_seconds":1,
  "format":"wav",
  "language":"zh-CN",
  "noise":"none",
  "source":"synthetic",
  "authorized":true,
  "redacted":true,
  "applicable_scenarios":["<实际场景ID>"]
}
```

sha256确认文件内容，byte_size确认体积，duration_seconds确认时长，language/noise描述覆盖条件，source/authorized/redacted说明来源与授权脱敏。勾选true不执行自动脱敏。

WAV校验真实时长；MP3目前校验文件头/hash/体积，不代表语音内容、解码或听感质量通过。超过16MiB、越界路径或hash/体积不符会拒绝。上传还需服务端确认上传契约和允许来源，登记本身不上传、不下载客户录音。

## 媒体 manifest {#media}

登记受控合成/授权脱敏文件的元信息，和文件一致才可使用。

**在哪里使用：** 扩展工具 → 测试资源 → 登记媒体manifest。

**填写或阅读示例：** 按本篇填真实文件path/hash/byte_size/时长及来源等，点击校验并登记。

**应该看到什么：** 返回登记与校验结果，不代表业务媒体处理通过。

**常见错误：** 复制示例hash，或登记原始客户录音并假填redacted=true。
