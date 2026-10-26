set working-directory := '../..'

cluster := env("INFERENCE_CLUSTER", "ttc-inference")
service := env("INFERENCE_SERVICE", "ttc-inference")
bucket := env("INFERENCE_MODEL_BUCKET", "dibbs-text-to-code")
resource_id := "service/" + cluster + "/" + service

# The GPU instance is listed via ECS: Managed Instances hides its EC2 instances from
# `aws ec2 describe-instances` listings.
[doc("Show tasks, the GPU instance, the wake/sleep alarms, and recent scaling activity")]
status:
    aws ecs describe-services --cluster {{ cluster }} --services {{ service }} \
      --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,taskDefinition:taskDefinition}' \
      --output table
    @instances="$(aws ecs list-container-instances --cluster {{ cluster }} --query 'containerInstanceArns' --output text)"; \
      if [ -n "$instances" ]; then \
        aws ecs describe-container-instances --cluster {{ cluster }} --container-instances $instances \
          --query 'containerInstances[].{instance:ec2InstanceId,status:status,type:attributes[?name==`ecs.instance-type`]|[0].value,runningTasks:runningTasksCount}' \
          --output table; \
      else echo "No GPU instance"; fi
    aws cloudwatch describe-alarms --alarm-names {{ service }}-wake {{ service }}-sleep \
      --query 'MetricAlarms[].{alarm:AlarmName,state:StateValue,since:StateUpdatedTimestamp}' \
      --output table
    aws application-autoscaling describe-scalable-targets --service-namespace ecs \
      --resource-ids {{ resource_id }} \
      --query 'ScalableTargets[0].SuspendedState' --output table
    aws application-autoscaling describe-scaling-activities --service-namespace ecs \
      --resource-id {{ resource_id }} --max-items 5 \
      --query 'ScalingActivities[].{time:StartTime,status:StatusCode,cause:Cause}' --output table

[doc("Start the service and hold it up (scale-in suspended) until `just inference release`")]
wake:
    aws application-autoscaling register-scalable-target --service-namespace ecs \
      --scalable-dimension ecs:service:DesiredCount --resource-id {{ resource_id }} \
      --suspended-state DynamicScalingInSuspended=true
    aws ecs update-service --cluster {{ cluster }} --service {{ service }} --desired-count 1 \
      --query 'service.desiredCount'

[doc("Let the idle alarm scale the service back to zero again")]
release:
    aws application-autoscaling register-scalable-target --service-namespace ecs \
      --scalable-dimension ecs:service:DesiredCount --resource-id {{ resource_id }} \
      --suspended-state DynamicScalingInSuspended=false

[doc("Stop the service now instead of waiting for the idle alarm")]
sleep: release
    aws ecs update-service --cluster {{ cluster }} --service {{ service }} --desired-count 0 \
      --query 'service.desiredCount'

[doc("Upload a saved sentence-transformers model directory to s3://<bucket>/models/NAME/")]
upload-model NAME DIR:
    aws s3 sync {{ DIR }} s3://{{ bucket }}/models/{{ NAME }}/ --exclude ".cache/*" --exclude "*/.cache/*"

[doc("Compare the served models on GPU vs CPU inside the running task (needs session-manager-plugin)")]
parity:
    aws s3 cp scripts/test_cases.json s3://{{ bucket }}/parity/test_cases.json
    aws ecs execute-command --cluster {{ cluster }} --container inference --interactive \
      --task "$(aws ecs list-tasks --cluster {{ cluster }} --service-name {{ service }} --query 'taskArns[0]' --output text)" \
      --command "python -m inference_service.parity --cases s3://{{ bucket }}/parity/test_cases.json"

[doc("Follow the service logs")]
logs:
    aws logs tail /ecs/{{ service }} --follow
