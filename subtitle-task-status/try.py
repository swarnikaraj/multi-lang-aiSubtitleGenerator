from task_process import process_video


BUCKET_NAME="tube_genius"
source_language='en'
target_language='hi'
task_id='hihiikhk'
video_id="aircAruvnKk"
operation_id='5823798974438978231'
result=process_video(BUCKET_NAME,task_id,operation_id,video_id,source_language,target_language)

print(result,"I am the result")