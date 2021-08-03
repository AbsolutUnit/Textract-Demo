import sys
import json
import fitz
import time
import boto3
import urllib.parse
from pdf2image import convert_from_path
from trp.trp2 import TDocument, TDocumentSchema, Document


class Conversion():
    s3 = boto3.client('s3')
    textract = boto3.client("textract", region_name='us-east-2')
    sqs = boto3.client("sqs", region_name='us-east-2')
    sns = boto3.client("sns", region_name='us-east-2')
    bucket = "bucketofpdfs"
    job_ID = ""
    arn = ""
    document_name = ""

    snq_URL = ""
    sns_ARN = ""
    typeof = ""

    def main(self, bucket_name, document_name):
        self.arn = 'insert arn'
        self.document_name = document_name
        self.typeof = "Analysis"

        self.queue()
        self.execute("Analysis")
        self.dequeue()

    def queue(self):
        sns_Topic = self.document_name.replace('.pdf', '') + "_textract_noti_" + str(int(time.time() * 1000))
        resp = self.sns.create_topic(Name=sns_Topic)
        self.sns_ARN = resp['TopicArn']

        queue_label = self.document_name.replace('.pdf', '') + "_textract_queue_" + str(int(time.time() * 1000))
        self.sqs.create_queue(QueueName=queue_label)
        self.snq_URL = self.sqs.get_queue_url(QueueName=queue_label)['QueueUrl']

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

    def execute(self, typeof):
        self.typeof = typeof
        valid_execution = False
        complete_flag = False

        if self.typeof == "Detection":
            exe = self.textract.start_document_text_detection(
                DocumentLocation={'S3Object': {'Bucket': self.bucket, 'Name': self.document_name}},
                NotificationChannel={'RoleArn': self.arn, 'SNSTopicArn': self.sns_ARN})
            valid_execution = True
        elif self.typeof == "Analysis":
            print("Analysis Started")
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
                                                MaxNumberOfMessages=10)

            if response:

                if 'Messages' not in response:
                    if skip < 40:
                        print('No Resp', end='')
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

                    if str(msg['JobId']) == exe['JobId']:
                        complete_flag = True
                        retval = self.refactor_json(self.parse(msg['JobId']))

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
        res = []
        while not fin:

            if self.typeof == "Analysis":
                if tok == None:
                    exe = self.textract.get_document_analysis(JobId=ID,
                                                              MaxResults=max_res)
                else:
                    exe = self.textract.get_document_analysis(JobId=ID,
                                                              MaxResults=max_res,
                                                              NextToken=tok)
            elif self.typeof == "Detection":
                if tok == None:
                    exe = self.textract.get_document_text_detection(JobId=ID,
                                                                    MaxResults=max_res)
                else:
                    exe = self.textract.get_document_text_detection(JobId=ID,
                                                                    MaxResults=max_res,
                                                                    NextToken=tok)

            if 'NextToken' in exe:
                tok = exe['NextToken']
            else:
                fin = True
            # print(exe['Blocks'])
            pages.append(exe)

        return json.dumps(pages)

    def refactor_json(self, json_file):
        ref = Document(json_file)
        pages = []
        for page in ref.pages:
            tables = []
            for table in page.tables:
                # Column as separate from data (have to fix)
                table_ex = []
                for r, row in enumerate(table.rows):
                    row_ex = []
                    for c, cell in enumerate(row.cells):
                        row_ex.append(cell.text.strip())
                    if row_ex:
                        table_ex.append(row_ex)
                if table_ex:
                    tables.append(table_ex)
            if tables:
                pages.append(tables)
        return json.dumps(pages)


# class Images():
#     s3 = boto3.client('s3')                       Depreciated method, only pulls actual
#     bucket = "bucketofimages                      images, meaning text or formatted tables
#     doc = None                                    aren't read by the method, and most of the time
#     doc_name = ""                                 Logos and seals are all that are returned

#     def main(self, bucket_in, document_name):
#         self.bucket = "bucketofimages"
#         self.doc_name = document_name
#         self.doc = fitz.open(document_name)
#         self.parse()

#     def parse(self):
#         for i in range(len(self.doc)):
#             for images in self.doc.getPageImageList(i):
#                 x = images[0]
#                 pixel = fitz.Pixmap(self.doc, x)
#                 if pixel.n - pixel.alpha < 4:
#                     pixel.writePNG("")
#                 else:
#                     pix1 = fitz.Pixmap(fitz.csRGB, pixel)
#                     pix1.writePNG("")
#                     pix1 = None
#                 pixel = None

def lambda_handler(event, context):
    an = Conversion()

    b = event['Records'][0]['s3']['bucket']['name']
    doc = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    try:
        an.main(b, doc)
        print("Success")
        return
    except Exception as e:
        print("Error! ", e)
        raise e
