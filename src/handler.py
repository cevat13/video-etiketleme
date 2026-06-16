import json
import os
import time
import logging
import urllib.parse
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

rekognition = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])


def _start_label_detection(bucket: str, key: str) -> str:
    response = rekognition.start_label_detection(
        Video={'S3Object': {'Bucket': bucket, 'Name': key}},
        MinConfidence=60.0
    )
    return response['JobId']


def _wait_for_job(job_id: str, poll_interval: int = 10, max_wait: int = 840) -> dict:
    elapsed = 0
    while elapsed < max_wait:
        result = rekognition.get_label_detection(JobId=job_id, SortBy='TIMESTAMP')
        status = result['JobStatus']
        logger.info(f"[{elapsed}s] Job status: {status}")

        if status == 'SUCCEEDED':
            return result
        if status == 'FAILED':
            raise RuntimeError(f"Rekognition job failed: {result.get('StatusMessage')}")

        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"Job timed out after {max_wait}s. Job ID: {job_id}")


def _collect_labels(first_result: dict, job_id: str) -> list:
    labels = list(first_result.get('Labels', []))
    next_token = first_result.get('NextToken')
    while next_token:
        page = rekognition.get_label_detection(JobId=job_id, NextToken=next_token, SortBy='TIMESTAMP')
        labels.extend(page.get('Labels', []))
        next_token = page.get('NextToken')
    return labels


def _deduplicate(labels: list) -> list:
    best = {}
    for item in labels:
        name = item['Label']['Name']
        confidence = item['Label']['Confidence']
        if name not in best or confidence > best[name]['Label']['Confidence']:
            best[name] = item
    return sorted(best.values(), key=lambda x: x['Label']['Confidence'], reverse=True)


def _save_to_dynamodb(bucket: str, key: str, job_id: str, labels: list, video_meta: dict):
    table.put_item(Item={
        'video_key': key,
        'analyzed_at': datetime.now(timezone.utc).isoformat(),
        'bucket': bucket,
        'job_id': job_id,
        'label_count': len(labels),
        'duration_seconds': str(round(video_meta.get('DurationMillis', 0) / 1000, 1)),
        'labels': [
            {'name': item['Label']['Name'], 'confidence': str(round(item['Label']['Confidence'], 2))}
            for item in labels
        ]
    })


def _print_results(bucket: str, key: str, job_id: str, labels: list):
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  Video : {key}")
    print(f"  Bucket: {bucket}")
    print(f"  Job ID: {job_id}")
    print(sep)
    print(f"  {'#':<5} {'Label':<35} {'Confidence':>12}")
    print("-" * 70)
    for i, item in enumerate(labels, start=1):
        name = item['Label']['Name']
        confidence = item['Label']['Confidence']
        bar = "▓" * int(confidence / 5) + "░" * (20 - int(confidence / 5))
        print(f"  {i:<5} {name:<35} {confidence:>8.2f}%  {bar}")
    print(sep)
    print(f"  Total: {len(labels)} unique labels detected.")
    print(f"{sep}\n")


def lambda_handler(event: dict, context) -> dict:
    logger.info(f"Event: {json.dumps(event)}")

    try:
        record = event['Records'][0]['s3']
        bucket_name = record['bucket']['name']
        object_key = urllib.parse.unquote_plus(record['object']['key'])
        object_size = record['object'].get('size', 0)
    except (KeyError, IndexError) as e:
        raise ValueError(f"Invalid S3 event: {e}") from e

    logger.info(f"Processing: s3://{bucket_name}/{object_key} ({object_size / 1024 / 1024:.2f} MB)")

    job_id = _start_label_detection(bucket_name, object_key)
    logger.info(f"Job ID: {job_id}")

    result = _wait_for_job(job_id)
    video_meta = result.get('VideoMetadata', {})

    labels = _deduplicate(_collect_labels(result, job_id))

    _print_results(bucket_name, object_key, job_id, labels)
    _save_to_dynamodb(bucket_name, object_key, job_id, labels, video_meta)

    return {
        'statusCode': 200,
        'bucket': bucket_name,
        'key': object_key,
        'job_id': job_id,
        'label_count': len(labels),
        'labels': [
            {'name': item['Label']['Name'], 'confidence': round(item['Label']['Confidence'], 2)}
            for item in labels
        ]
    }
