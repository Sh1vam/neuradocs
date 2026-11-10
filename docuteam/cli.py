# cli.py
import argparse
from config import RELEASE, WORKSPACE
from feedback import record_feedback          # Chapter 06, Part C
from knowledge import ingest
from orchestrator import find_request, handle

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('ask')
    a.add_argument('question')
    a.add_argument('--url', action='append', default=[])
    sub.add_parser('ingest')
    f = sub.add_parser('feedback')
    f.add_argument('request_id')
    f.add_argument('verdict', choices=['approved', 'edited', 'rejected'])
    f.add_argument('--edit', default=None)
    f.add_argument('--reason', default='')
    args = ap.parse_args()

    if args.cmd == 'ingest':
        print(ingest(), 'chunks indexed')
    elif args.cmd == 'ask':
        r = handle(args.question, urls=args.url)
        print(r['answer'])
        print('\nroute:', r['route'], '| sources:', ', '.join(r['sources']), '| id:', r['request_id'])
    else:
        rec = find_request(args.request_id)
        record_feedback(str(WORKSPACE / 'logs' / 'feedback.jsonl'), args.request_id, rec['question'],
                        rec['route'], RELEASE, rec['answer'], args.verdict,
                        human_edit=args.edit, reason=args.reason)

if __name__ == '__main__':
    main()