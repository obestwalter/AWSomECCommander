from beeswithmachineguns.bees import attack

if __name__ == '__main__':
    # bees up -s 10 -z us-east-1a -k aws-ec2-us-east-1
    for _ in range(100):
        attack(
            'http://update-bridge-oliver-y5rxgpaear.elasticbeanstalk.com/',
            n=1000, c=100,
            post_file='post_data'
        )
