import sys
import json
import time
import urllib.parse
import boto3
from enum import Enum

s3 = boto3.client('s3')

class PDF_Conversion():
    s3 = boto3.client('s3')
    textract = boto3.client("textract")
    sqs = boto3.client("sqs")
    sns = boto3.client("sns")
    bucket = "bucketofpdfs"
    job_ID = ""
    arn = ""
    document_name = ""

    snq_URL = ""
    sns_ARN = ""
    type = ""

    def main(self, bucket_name, document_name):
        self.arn = 'arn:aws:iam::125223209031:role/service-role/pdfExtractorRole'
        self.document_name = document_name
        self.type = "Analysis"

        self.queue()
        self.execute("Analysis")
        self.dequeue()

    def queue(self):
        sns_Topic = self.document_name.replace('.pdf', '') + "_textract_noti_" + str(int(time.time() * 1000))
        resp = self.sns.create_topic(Name = sns_Topic)
        self.sns_ARN = resp['TopicArn']

        queue_label = self.document_name.replace('.pdf', '') + "_textract_queue_" + str(int(time.time() * 1000))
        self.sqs.create_queue(QueueName = queue_label)
        self.snq_URL = self.sqs.get_queue_url(QueueName = queue_label)['QueueUrl']

        qArn = self.sqs.get_queue_attributes(QueueUrl=self.snq_URL,
                                             AttributeNames=['QueueArn'])['Attributes']
        self.sns.subscribe(
        TopicArn=self.sns_ARN,
        Protocol='sqs',
        Endpoint=qArn['QueueArn'])

        policy = """{{
        "Version":"2012-10-17",
        "Statement":[
        {{
            "Sid":"MyPolicy",
            "Effect":"Allow",
            "Principal" : {{"AWS" : "*"}},
            "Action":"SQS:SendMessage",
            "Resource": "{}",
            "Condition":{{
            "ArnEquals":{{
            "aws:SourceArn": "{}"
            }}
        }}
        }}
        ]
        }}""".format(qArn['QueueArn'], self.sns_ARN)

        resp_val = self.sqs.set_queue_attributes(
            QueueUrl=self.snq_URL,
            Attributes={'Policy': policy})


    def dequeue(self):
        self.sqs.delete_queue(QueueUrl=self.snq_URL)
        self.sns.delete_topic(TopicArn=self.sns_ARN)


    def store(self, obj):
        json_formatted = str(obj)
        doc_name = self.document_name.replace('.pdf', '') + '.json'

        s3.put_object(Body=json_formatted, Bucket=self.bucket, Key=doc_name)


    def execute(self, type):
        self.type = type
        valid_execution = False
        complete_flag = False

        if self.type == "Detection":
            exe = self.textract.start_document_text_detection(
                DocumentLocation={'S3Object': {'Bucket': self.bucket, 'Name': self.document_name}},
                NotificationChannel={'RoleArn': self.arn, 'SNSTopicArn': self.sns_ARN})
            valid_execution = True
        elif self.type == "Analysis":
            exe = self.textract.start_document_analysis(
                DocumentLocation={'S3Object': {'Bucket': self.bucket, 'Name': self.document_name}},
                FeatureTypes=["TABLES"],
                NotificationChannel={'RoleArn': self.arn, 'SNSTopicArn': self.sns_ARN})
            valid_execution = True

        if not valid_execution:
            print("Type invalid. Try again.")
            return

        skip = 0
        while not complete_flag:
            response = self.sqs.receive_message(QueueUrl=self.snq_URL, MessageAttributeNames=['ALL'],
                MaxNumberOfMessages = 10)

            if response:

                if 'Messages' not in response:
                    if skip < 40:
                        print('.', end='')
                        skip += 1
                    else:
                        print()
                        skip = 0
                    sys.stdout.flush()
                    time.sleep(5)
                    continue

                for each in response['Messages']:

                    info = json.loads(each['Body'])
                    msg = json.loads(info['Message'])

                    if str(msg['JobID']) == exe['JobId']:
                        complete_flag = True
                        retval = self.parse(msg['JobId'])
                        self.store(retval)
                        self.sqs.delete_message(QueueUrl=self.snq_URL,
                                        ReceiptHandle=each['ReceiptHandle'])
                    else:
                        self.sqs.delete_message(QueueUrl=self.snq_URL,
                                        ReceiptHandle=each['ReceiptHandle'])
                        continue


    def parse(self, ID):
        max_res = 1000
        tok = None
        fin = False
        pages = []

        while not fin:

            resp = None

            if self.type == "Analysis":
                if tok == None:
                    exe = self.textract.get_document_analysis(JobId=ID,
                                                              MaxResults=max_res)
                else:
                    exe = self.textract.get_document_analysis(JobId=ID,
                                                          MaxResults=max_res,
                                                          NextToken=tok)
            elif self.type == "Detection":
                if tok == None:
                    exe = self.textract.get_document_detection(JobId=ID,
                                                           MaxResults=max_res)
                else:
                    exe = self.textract.get_document_detection(JobId=ID,
                                                           MaxResults=max_res,
                                                           NextToken=tok)

            pages.append(exe)
            if 'NextToken' in exe:
                tok = exe['NextToken']
            else:
                fin = True

        return json.dump(pages)


def lambda_handler(event, context):
    an = PDF_Conversion()

    b = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    try:
        an.main(b, key)
        print("Success")
        return
    except Exception as e:
        print("Error! ", e)
        raise e