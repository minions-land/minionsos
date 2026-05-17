## Reviewer

1. 是这样的，实际上审稿过程是一个loop，每一个loop要针对多个subspect生成subagent负责一个板块，读paper或者代码（根据suspect的subagent所负责的内容）。然后生成一个统一的审稿意见，其实就是按照templete合在一起。然后成为一个review意见，subagent关闭。其实就是多个subagent每一轮一起模拟一位reviewer.然后这是一轮。然后生成新的一轮。重复三到五次。最少三次。因为审稿人会有三到五个。这个几个就根据情况来。一开始可以多点。后面如果还有继续的审稿可以少点。或者如果多轮审稿意见都差不多。可以就不要新的轮次了。然后最后reviewer agent返回每一个审稿人的审稿意见。

2. 需要。除非直接给出了Accept或者Strong Accept，否则一定要求作者返回这次审稿的revision，继续审稿。如果给出了Accept或者Strong Accept了，那就要求作者修改后成为camera-ready版本，就不用再提交给reviewer agents了，就返回给人类了（Tex zip的压缩包，可pull提交的github代码整合，以及pdf，包括一些必要的补充材料的zip）

3. 只提Weakness和Questions，包括可能有limitaion。但是不说优点。因为说优点没用。但是需要有个总体判断。比如你提不出优点就肯定是比较好的结果。

4. 肯定需要列出证据。每一个点评都要列出证据。没有证据就是幻觉。证据需要包括哪个文章（最好甚至有arxiv链接附上，或者相关的真实bib）等。反正具体形式都可以，但是我们review一定强调证据！！！！！！

5. 多个skill吧，其实就是开启每一个subspect subagent的prompt 大概可以这么理解。当然肯定还有一些其他的。

6. 要和paper一一对应。否则就乱了。