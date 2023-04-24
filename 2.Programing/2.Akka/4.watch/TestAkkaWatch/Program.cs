using Akka.Actor;

namespace TestAkkaWatch
{
    //class Program
    //{
    //    static void Main(string[] args)
    //    {
    //        var system = ActorSystem.Create("MySystem");

    //        var printer = system.ActorOf<Printer>("printer");

    //        printer.Tell("Hello, world!");

    //        Console.ReadLine();

    //        system.Terminate().Wait();
    //    }
    //}

    //class Printer : ReceiveActor
    //{
    //    public Printer()
    //    {
    //        Receive<string>(s => Console.WriteLine(s));
    //        Context.Watch(Context.Parent);
    //    }
    //}

    class Program
    {
        static void Main(string[] args)
        {
            var system = ActorSystem.Create("MySystem");
            var targetActor = system.ActorOf<TargetActor>("targetActor");
            var watcherActor = system.ActorOf(Props.Create(() => new WatcherActor(targetActor)), "watcherActor");

            // 감시 대상 액터 종료
            system.Stop(targetActor);

            Console.ReadLine();
        }
    }

    // 감시자 액터 정의
    public class WatcherActor : ReceiveActor
    {
        private readonly IActorRef _target;

        public WatcherActor(IActorRef target)
        {
            _target = target;
            // Watch 메시지를 전송하여 관찰 대상 액터를 감시합니다.
            Context.Watch(target);

            Receive<Terminated>(terminated =>
            {
                // 감시 대상 액터가 종료되면 이 메시지를 받게 됩니다.
                Console.WriteLine($"Actor {_target.Path.Name} has been terminated");
            });
        }
    }

    // 감시 대상 액터 정의
    public class TargetActor : ReceiveActor
    {
        public TargetActor()
        {
            Receive<string>(message => Console.WriteLine($"Received message: {message}"));
        }

        protected override void PreStart()
        {
            Console.WriteLine($"Actor {Self.Path.Name} has started");
        }

        protected override void PostStop()
        {
            Console.WriteLine($"Actor {Self.Path.Name} has been stopped");
        }
    }
}
