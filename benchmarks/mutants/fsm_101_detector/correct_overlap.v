module top_module(input clk, input reset, input bit_in, output reg found);
    reg [1:0] state;
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2;

    always @(posedge clk) begin
        if (reset) begin
            state <= S0;
            found <= 1'b0;
        end else begin
            found <= 1'b0;
            case (state)
                S0: state <= bit_in ? S1 : S0;
                S1: state <= bit_in ? S1 : S10;
                S10: begin
                    if (bit_in) begin
                        state <= S1;
                        found <= 1'b1;
                    end else begin
                        state <= S0;
                    end
                end
                default: state <= S0;
            endcase
        end
    end
endmodule
