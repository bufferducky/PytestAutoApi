import { ElMessageBox } from 'element-plus';
let pending = false;
/** 同时只接受一个范围确认；取消/关闭正常返回 false，不作为 API 错误展示。 */
export async function confirmAction(message: string, title = '请确认操作'): Promise<boolean> {
  if (pending) return false;
  pending = true;
  try {
    await ElMessageBox.confirm(message, title, { confirmButtonText: '确认', cancelButtonText: '取消',
      type: 'warning', closeOnClickModal: false, distinguishCancelAndClose: true });
    return true;
  } catch { return false; }
  finally { pending = false; }
}
