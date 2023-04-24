using Akka.Actor;
using TestAkkaFSM.Actors;
using TestAkkaFSM.Messages;

class Program
{
    static void Main(string[] args)
    {
        var system = ActorSystem.Create("MySystem");
        //IActorRef mainActor = system.ActorOf(Props.Create(() => new MainActor()), "mainactor");
        IActorRef mainActor = system.ActorOf<MainActor>("mainactor");

        mainActor.Tell(new StateApple());        
        mainActor.Tell("Eat");
        mainActor.Tell("Read");

        //mainActor.Tell(new StateBook());
        mainActor.Tell("Eat");
        mainActor.Tell("Read");

        Console.ReadLine();
    }

}