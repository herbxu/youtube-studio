const path=require('node:path');
module.exports=function runtime(ep){
 const parent=path.resolve(__dirname,'../..'), works=path.resolve(process.env.YOUTUBE_WORKS_ROOT||path.join(parent,'youtube')), bench=path.resolve(process.env.YOUTUBE_WORKBENCH_ROOT||path.join(parent,'youtube-workbench'));
 for (const [base,ns] of [[works,'episodes'],[bench,'examples']])
  if(path.dirname(ep)===path.join(base,ns))return path.join(bench,'runtime',ns,path.basename(ep));
 return ep;
};
