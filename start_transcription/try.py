from task_process import process_youtube_audio

video_url='https://www.youtube.com/watch?v=aircAruvnKk&list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi'
BUCKET_NAME="tube_genius"
source_language='en'
target_language='hi'
user_id='677e9bb7eb111b87ea1893d2'
task_id='hihiikhk'
result=process_youtube_audio(video_url, BUCKET_NAME,source_language,target_language,user_id,task_id)

print(result,"I am the result")