import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import type { Asset, Job, Project } from "../api/types";

export const sampleProject: Project = { id:"p-ui",name:"页面测试项目",description:"页面验收",status:"draft",video_ratio:"9:16",duration_seconds:5,created_at:"2026-10-03T00:00:00Z",updated_at:"2026-10-03T00:00:00Z",asset_count:0,job_count:0,token_usage_status:"available",token_total:2000,token_input:1200,token_output:800 };
export const sampleJob: Job = { id:"j-ui",project_id:"p-ui",provider:"agnes",status:"failed",progress:25,current_node:"generate_outfits",workflow_version:"v2",created_at:sampleProject.created_at,error_message:"生成服务暂时不可用" };
export type UiCall = {path:string; method:string; body:RequestInit["body"]};

export function mountPage(route:string, options:{mode?:string;job?:Partial<Job>;tokenStatus?:string}={}) {
  const calls:UiCall[]=[];
  const assets:Asset[]=[];
  const project={...sampleProject,token_usage_status:options.tokenStatus ?? "available"};
  const job={...sampleJob,...options.job};
  let mode=options.mode ?? "mock";
  const backups=[{id:"b-ui",archive_name:"完整备份.zip",file_count:4,file_size:1024,created_at:sampleProject.created_at}];
  const fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=new URL(String(input),"http://localhost").pathname.replace(/^\/api/,"");
    const method=init?.method ?? "GET";
    calls.push({path,method,body:init?.body});
    let data:unknown=[];
    if(["/projects","/dashboard/recent-projects"].includes(path)) data=[{...project,asset_count:assets.length}];
    if(path==="/projects/p-ui") data={...project,status:assets.length===4?"ready":"draft",asset_count:assets.length};
    if(path==="/projects" && method==="POST") data={...project,...JSON.parse(String(init?.body))};
    if(path==="/projects/p-ui/assets") data=assets;
    if(path.startsWith("/projects/p-ui/assets/") && method==="POST") {
      const form=init?.body as FormData; const file=form.get("file") as File;
      const asset={id:`a-${assets.length}`,project_id:project.id,asset_type:path.endsWith("model")?"model":"clothing",original_name:file.name,display_name:String(form.get("name")??"模特图"),stored_path:"test.png",mime_type:file.type,file_size:file.size,sha256:"test",width:1,height:1,slot_index:form.has("slot_index")?Number(form.get("slot_index")):null,created_at:project.created_at,file_url:"/test.png",thumbnail_url:"/test.png"} as Asset;
      assets.push(asset); data=asset;
    }
    if(["/jobs","/dashboard/recent-jobs"].includes(path)) data=[job];
    if(path==="/jobs/j-ui" || (path==="/projects/p-ui/jobs" && method==="POST")) data=job;
    if(path==="/jobs/j-ui/logs") data=[{id:"log",job_id:job.id,node_name:"generate_outfits",sequence:1,status:"failed",error_message:job.error_message,input_summary:"输入已校验",output_summary:"",created_at:project.created_at}];
    if(path==="/jobs/j-ui/outputs") data=[{id:"o-ui",job_id:job.id,project_id:project.id,video_url:"/video.mp4",thumbnail_url:"/cover.png",duration:5,width:720,height:1280}];
    if(path==="/settings") { if(method==="PATCH") mode=JSON.parse(String(init?.body)).mode; data={mode}; }
    if(path==="/providers") data=[{name:"mock",label:"Mock 演示",description:"本地演示",configured:true},{name:"agnes",label:"Agnes 真实生成",description:"图像与视频模型",configured:true}];
    if(path==="/backups" || path==="/backups/export") data=path.endsWith("export")?backups[0]:backups;
    if(path==="/backups/import") data={project_count:1};
    if(path==="/dashboard/summary") data={project_count:1,asset_count:assets.length,job_count:1,succeeded_count:job.status==="succeeded"?1:0};
    return new Response(JSON.stringify({success:true,data}),{status:method==="POST"?201:200});
  });
  vi.stubGlobal("fetch",fetchMock);
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  const view=render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
  return {client,calls,assets,fetchMock,...view};
}
