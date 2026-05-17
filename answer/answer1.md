1. C 不以单篇论文为目的。而是偏开放式的科学发现。可以形成多篇论文，也可以专攻一个主题做论文。这里面涉及到一个NoterAgent，Noter Agent作为这个工作流里面唯一一个和人类进行交互的工作流，其可以觉得具体是开放式科学发现，还是很指定的解决一个问题。但是重要的点是：不能限制扼杀Agent本身的创造能力

2. Experts是整个工作流在Agents层面的脑子，是多个专家，是需要人类设定的。他可以非常具体，比如具体的CV里面的Transformer方法的专家，但是也可以是你这里面写的比较泛化的，都可以。

3. Experiments的Agent最大的功能是掌管GPU，其是管理者，充分掌握GPU资源和CPU存储，内存资源，其负责接受来自专家团的需要GPU的实验内容，分配好GPU给一个subagents，然后完成实验。

4. Paper Agents负责完整的论文LaTeX写作（他需要论文的LaTeX Format），画python的模型图，制表等。我觉得也可以包装吧，需要具备一定的包装自主能力。

5. 模拟外部审稿人，实际上Reviewer Agent他模拟的是会议的Area Chair或者期刊的Editor，他负责生成虚拟的Reviewer Subagents，从多个角度进行评估。这个具体的还要聊。他返回的就是审稿人的意见。

6. Noter Agent的作用是作为我们MinionsOS（其中MinionsOS就是基于EACN的全自主科学发现的工作流）里唯一一个和人进行交互的agent，是用来人来发布任务，然后全程参与和这个任务有关的所有任务，并负责记录的。记录所有的过程，记录所有的经验，记录这个当中的每一个所谓的工作流调用。就是记录员。最后任务结束的时候进行总结经验。这个经验是可以被复用的。大致是这样。

7. Noter在主branch把，然后其他的各自branch然后合并。毕竟noter是人类和EACN或者说MinionsOS唯一的接口

8. 不，每个Agent在生成定义的时候，需要明确Role/Cando/cannotdo/outputformat，有些是可以默认的，但是Role和Cando是一定要有的。