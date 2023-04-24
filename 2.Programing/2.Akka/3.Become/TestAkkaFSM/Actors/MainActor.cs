using Akka.Actor;
using Akka.Event;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using TestAkkaFSM.Messages;

namespace TestAkkaFSM.Actors
{
    //public  class MainActor : UntypedActor
    //{
    //    private ILoggingAdapter log = Context.GetLogger();
    //    public MainActor() 
    //    {

    //    }

    //    protected override void OnReceive(object message)
    //    {
    //        log.Info("Normal Actor.");
    //        switch(message as string)
    //        {
    //            case "StateApple":
    //                Become(Apple);
    //                break;
    //            case "StateBook":
    //                Become(Book);
    //                break;
    //            default:
    //                log.Info("wrong state!");
    //                break;
    //        }
    //    }
    //    private void Apple(object message)
    //    {
    //        log.Info("State : Apple");
    //        switch(message as string)
    //        {
    //            case "Eat":
    //                log.Info("Eat!");
    //                break;
    //            default:
    //                log.Info($"Unknown Message is {message}");
    //                break;
    //        }

    //    }

    //    private void Book(object message)
    //    {
    //        log.Info("state : Book");
    //        switch(message as string) 
    //        {
    //            case "Read":
    //                log.Info("Read!");
    //                break;
    //            default:
    //                log.Info($"Unknown Message is {message}");
    //                break;
    //        }
    //    }

    //    public void Dispose()
    //    {

    //    }
    //}
    public class MainActor : ReceiveActor,IDisposable
    {
        private ILoggingAdapter log = Context.GetLogger();
        public MainActor()
        {
            Receive<StateApple>(msg =>
            {
                Become(Apple);
            });
            Receive<StateBook>(msg =>
            {
                Become(Book);
            });
        }

        private void Apple(object message)
        {
            log.Info("State : Apple");
            switch (message as string)
            {
                case "Eat":
                    log.Info("Eat!");
                    break;
                default:
                    log.Info($"Unknown Message is {message}");
                    Become(Book);
                    break;
            }

        }

        private void Book(object message)
        {
            log.Info("state : Book");
            switch (message as string)
            {
                case "Read":
                    log.Info("Read!");
                    break;
                default:
                    log.Info($"Unknown Message is {message}");
                    break;
            }
        }

        public void Dispose()
        {

        }
    }
}
