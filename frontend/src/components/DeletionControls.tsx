import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Modal, message } from "antd";
import { api } from "../api/client";
import type { Job, Project } from "../api/types";

export const isStoppedJob = (job: Pick<Job, "status">) => ["succeeded", "failed", "canceled"].includes(job.status);

function DeleteButton({ kind, id, name, disabled = false, onDeleted }: {
  kind: "project" | "job"; id: string; name: string; disabled?: boolean; onDeleted?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const label = kind === "project" ? "项目" : "任务";
  const mutation = useMutation({
    mutationFn: () => kind === "project" ? api.projects.delete(id) : api.jobs.delete(id),
    onSuccess: async () => {
      setOpen(false);
      // Both entry points address the same underlying project/job. Refresh all
      // related screens, including cached screens visited before the deletion.
      await client.invalidateQueries({ predicate: (query) => ["dashboard", "projects", "project", "assets", "jobs", "job", "logs", "artifacts", "outputs"].includes(String(query.queryKey[0])) });
      message.success(`${label}已删除`);
      onDeleted?.();
    },
    onError: (error: Error) => message.error(error.message || `${label}删除失败`),
  });
  return <>
    <Button type="link" danger disabled={disabled || mutation.isPending} aria-label={`删除${label} ${name}`} title={disabled ? "任务正在执行，请先取消任务再删除" : `删除${label}`} onClick={() => setOpen(true)}>删除</Button>
    <Modal title={`删除${label}？`} open={open} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }} confirmLoading={mutation.isPending} onOk={() => mutation.mutate()} onCancel={() => { if (!mutation.isPending) setOpen(false); }}>
      <p>{kind === "project" ? `删除“${name}”后，工作台、换装项目和素材库将同步移除该项目。生成记录、历史视频和日志继续保留，可在生成记录中单独删除。` : `删除任务“${name}”将同时移除生成队列和生成记录中的这一任务，并清理其日志、Token 用量、中间产物和视频。所属项目及其他任务继续保留。`}</p>
    </Modal>
  </>;
}

export function DeleteProjectButton({ project }: { project: Project }) {
  return <DeleteButton kind="project" id={project.id} name={project.name} />;
}

export function DeleteJobButton({ job, onDeleted }: { job: Job; onDeleted?: () => void }) {
  return <DeleteButton kind="job" id={job.id} name={job.id.slice(0, 8)} disabled={!isStoppedJob(job)} onDeleted={onDeleted} />;
}
