// ============================================================
// Admin: BotConfig — bot config form (feishu webhook, QQ token,
// schedule, enable toggle).
// ============================================================

import { useState, useEffect, type FormEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";

interface BotConfigData {
  feishu_webhook: string;
  qq_token: string;
  schedule: string;
  enabled: boolean;
}

// ---- defaults ----
const DEFAULT_CONFIG: BotConfigData = {
  feishu_webhook: "",
  qq_token: "",
  schedule: "0 9 * * *",
  enabled: false,
};

export default function BotConfig() {
  const [config, setConfig] = useState<BotConfigData>(DEFAULT_CONFIG);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  // Simulate loading config — replace with real API call
  useEffect(() => {
    // TODO: fetch actual config from /api/bot/config
    setConfig({
      feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
      qq_token: "",
      schedule: "0 9 * * *",
      enabled: true,
    });
  }, []);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);
    try {
      // TODO: POST /api/bot/config
      await new Promise((r) => setTimeout(r, 500));
      setMsg({ type: "success", text: "机器人配置已更新" });
    } catch {
      setMsg({ type: "error", text: "配置保存失败" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <Typography variant="h4" gutterBottom>
        机器人配置 (管理员)
      </Typography>

      <Paper sx={{ p: 3 }}>
        {msg && (
          <Alert severity={msg.type} sx={{ mb: 2 }}>
            {msg.text}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSave} noValidate>
          <FormControlLabel
            control={
              <Switch
                checked={config.enabled}
                onChange={(e) =>
                  setConfig({ ...config, enabled: e.target.checked })
                }
              />
            }
            label="启用机器人"
          />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            关闭后将停止所有平台的自动推送。
          </Typography>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            飞书机器人
          </Typography>
          <TextField
            fullWidth
            label="Webhook URL"
            margin="normal"
            value={config.feishu_webhook}
            onChange={(e) =>
              setConfig({ ...config, feishu_webhook: e.target.value })
            }
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
            helperText="飞书群机器人的 Webhook 地址"
          />

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            QQ 机器人
          </Typography>
          <TextField
            fullWidth
            label="QQ Bot Token"
            margin="normal"
            value={config.qq_token}
            onChange={(e) =>
              setConfig({ ...config, qq_token: e.target.value })
            }
            type="password"
            placeholder="输入 QQ Bot 的 access_token"
            helperText="QQ Bot 的访问令牌，请妥善保管"
          />

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            推送计划
          </Typography>
          <FormControl fullWidth margin="normal" size="small">
            <InputLabel>推送频率</InputLabel>
            <Select
              value={config.schedule}
              label="推送频率"
              onChange={(e) =>
                setConfig({ ...config, schedule: e.target.value })
              }
            >
              <MenuItem value="0 9 * * *">每天 09:00</MenuItem>
              <MenuItem value="0 8 * * *">每天 08:00</MenuItem>
              <MenuItem value="0 12 * * *">每天 12:00</MenuItem>
              <MenuItem value="0 20 * * *">每天 20:00</MenuItem>
              <MenuItem value="0 9 * * 1">每周一 09:00</MenuItem>
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label="Cron 表达式 (自定义)"
            margin="normal"
            value={config.schedule}
            onChange={(e) =>
              setConfig({ ...config, schedule: e.target.value })
            }
            size="small"
            helperText='格式: "分 时 日 月 周" (如: 0 9 * * * 表示每天9点)'
          />

          <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
            <Button
              type="submit"
              variant="contained"
              disabled={saving}
            >
              {saving ? <CircularProgress size={20} /> : "保存配置"}
            </Button>
            <Button
              variant="outlined"
              onClick={() =>
                setConfig(DEFAULT_CONFIG)
              }
            >
              重置
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
