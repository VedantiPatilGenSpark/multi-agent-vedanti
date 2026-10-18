The task runs in a private subnet. Its security group has no inbound rules. Outbound traffic is TCP 443, so the task can reach Bedrock through a NAT gateway or a Bedrock VPC endpoint.

The task is started by hand, prints one score, and exits. Nothing on the internet connects to it.
